#!/usr/bin/env python3
"""etch - validate, export and deliver .drawio sources.

    etch validate [--page N] [--allow-external] [--profile P] <input.drawio>
    etch export   --format svg|png|pdf --output-root DIR [options] <input.drawio>
    etch deliver  --format svg|png|pdf --output-root DIR [options] <input.drawio>
    etch verify   --output-root DIR
    etch gc       --output-root DIR [--delete]

export builds a finished generation but leaves the current pointer where it is.
deliver does the same and then commits the pointer to the new generation.

stdout always carries the diagnostics JSON and nothing else; human-readable
lines go to stderr. --json is accepted for explicitness and changes nothing.

Contracts: contracts/exit-codes.md, contracts/diagnostics.schema.json,
contracts/delivery.md, contracts/profile.md, contracts/environment.md
"""

import os
import shutil
import signal
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import etch_delivery  # noqa: E402
import etch_export  # noqa: E402
import etch_profile  # noqa: E402
import etch_validate  # noqa: E402
from etch_report import Interrupted, Report, UsageError, sha256_file  # noqa: E402

FORMATS = ("svg", "png", "pdf")

FLAGS = {
    "validate": {"--allow-external", "--json"},
    "export": {"--allow-external", "--embed-xml", "--json"},
    "deliver": {"--allow-external", "--embed-xml", "--json"},
    "verify": {"--json"},
    "gc": {"--delete", "--json"},
}
VALUED = {
    "validate": {"--page", "--profile"},
    "export": {"--format", "--output-root", "--page", "--scale", "--content", "--profile"},
    "deliver": {"--format", "--output-root", "--page", "--scale", "--content", "--profile"},
    "verify": {"--output-root", "--profile"},
    "gc": {"--output-root", "--profile"},
}
TAKES_INPUT = ("validate", "export", "deliver")


# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------


def parse(argv):
    if not argv:
        raise UsageError("a subcommand is required: %s" % ", ".join(sorted(FLAGS)))
    command = argv[0]
    if command in ("-h", "--help"):
        sys.stderr.write(__doc__)
        raise SystemExit(0)
    if command not in FLAGS:
        raise UsageError("unknown subcommand: %s" % command)

    options = {
        "command": command,
        "page": 1,
        "scale": 2,
        "format": None,
        "output_root": None,
        "content": None,
        "profile": None,
        "input": None,
        "allow_external": False,
        "embed_xml": False,
        "delete": False,
    }
    rest = list(argv[1:])
    inputs = []
    while rest:
        token = rest.pop(0)
        if token in FLAGS[command]:
            options[token.lstrip("-").replace("-", "_")] = True
        elif token in VALUED[command]:
            if not rest:
                raise UsageError("%s needs a value" % token)
            options[token.lstrip("-").replace("-", "_")] = rest.pop(0)
        elif token.startswith("-") and token != "-":
            raise UsageError("unknown option for %s: %s" % (command, token))
        else:
            inputs.append(token)

    if command in TAKES_INPUT:
        if not inputs:
            raise UsageError("%s needs exactly one input .drawio file" % command)
        if len(inputs) > 1:
            raise UsageError("%s takes exactly one input, got %d" % (command, len(inputs)))
        options["input"] = inputs[0]
    elif inputs:
        raise UsageError("%s takes no positional arguments" % command)

    options["page"] = positive_integer(options["page"], "--page")
    if command in ("export", "deliver"):
        if options["format"] is None:
            raise UsageError("--format is required (one of %s)" % ", ".join(FORMATS))
        if options["format"] not in FORMATS:
            raise UsageError(
                "unsupported format %r; use one of %s" % (options["format"], ", ".join(FORMATS))
            )
        options["scale"] = positive_number(options["scale"], "--scale")
        if options["embed_xml"] and options["format"] != "svg":
            raise UsageError("--embed-xml only applies to svg")
    return options


def positive_integer(value, label):
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise UsageError("%s must be an integer of 1 or more" % label)
    if number < 1:
        raise UsageError("%s must be an integer of 1 or more" % label)
    return number


def positive_number(value, label):
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        raise UsageError("%s must be a positive number" % label)
    if not number > 0:
        raise UsageError("%s must be a positive number" % label)
    return number


def existing_file(path, label):
    if not os.path.exists(path):
        raise UsageError("%s does not exist: %s" % (label, path))
    if not os.path.isfile(path):
        raise UsageError("%s is not a regular file: %s" % (label, path))
    if not os.access(path, os.R_OK):
        raise UsageError("%s is not readable: %s" % (label, path))
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------


def command_validate(options, report, root_dir):
    etch_profile.resolve(options["profile"])
    source = existing_file(options["input"], "the input")
    try:
        etch_validate.validate(
            report,
            root_dir,
            source,
            page=options["page"],
            allow_external=options["allow_external"],
        )
    except etch_validate.Invalid:
        return 1
    return 0


def command_export(options, report, root_dir, commit_pointer):
    profile, _ = etch_profile.resolve(options["profile"])
    source = existing_file(options["input"], "the input")
    content = (
        existing_file(options["content"], "--content") if options["content"] else source
    )
    delivery = etch_delivery.Delivery(report, options["output_root"])
    command = etch_export.resolve_drawio(report)
    report.passed("dependency/drawio")

    workspace = tempfile.mkdtemp(dir=delivery.root, prefix=".etch-work.")
    try:
        h0 = sha256_file(source)
        try:
            etch_validate.validate(
                report,
                root_dir,
                content,
                page=options["page"],
                allow_external=options["allow_external"],
            )
        except etch_validate.Invalid:
            return 1

        work_copy = os.path.join(workspace, "content.drawio")
        shutil.copyfile(content, work_copy)
        h_final = sha256_file(work_copy)

        # S2: the one moment the master may change. Confirm nobody else moved it.
        etch_delivery.confirm_hash(report, source, h0, "pre-write")
        target = source
        if profile["proposal_mode"]:
            target = "%s.agent-proposal.drawio" % os.path.splitext(source)[0]
            with open(work_copy, "rb") as handle:
                etch_delivery.atomic_write(target, handle.read())
        elif h_final != h0:
            with open(work_copy, "rb") as handle:
                etch_delivery.atomic_write(target, handle.read())

        # S3: build the generation.
        staging = delivery.open_generation(h_final)
        stem = os.path.splitext(os.path.basename(source))[0]
        produced = os.path.join(staging, "%s.%s" % (stem, options["format"]))
        argv = etch_export.build_argv(
            command,
            work_copy,
            produced,
            options["format"],
            options["page"],
            options["scale"],
            options["embed_xml"],
        )
        try:
            etch_export.run_export(report, argv, os.path.join(workspace, "drawio.log"))
            etch_export.verify_output(report, produced, options["format"], options["embed_xml"])
        except etch_export.ExportFailed:
            delivery.discard()
            return 2

        artifacts = [
            {
                "path": os.path.basename(produced),
                "sha256": sha256_file(produced),
                "kind": options["format"],
            }
        ]

        # S4: the receipt covers the artifacts, never itself.
        delivery.write_receipt(
            etch_delivery.build_receipt(
                delivery.identifier,
                report.tool_version,
                profile["proposal_mode"],
                target,
                h_final,
                {
                    "command": command,
                    "version": etch_export.drawio_version(command),
                    "options": argv[1:],
                },
                etch_delivery.vendor_lock_record(root_dir),
                artifacts,
                list(report.checks),
            )
        )

        # S5: rename into place. From here the generation is immutable.
        final = delivery.commit_generation()
        report.passed("delivery/generation")
        for artifact in artifacts:
            report.artifact(
                os.path.join(final, artifact["path"]),
                artifact["kind"],
                digest=artifact["sha256"],
            )

        # S6: commit the pointer, once the delivered file is still ours.
        if commit_pointer:
            etch_delivery.confirm_hash(report, target, h_final, "pre-commit")
            if profile["proposal_mode"]:
                report.log(
                    "proposal mode: %s was written and current was left alone" % target
                )
            else:
                delivery.commit_pointer()
                report.passed("delivery/pointer")
        report.passed("delivery/handoff")
        return 0
    except etch_delivery.Conflict:
        return 3
    finally:
        delivery.discard()
        shutil.rmtree(workspace, ignore_errors=True)


def command_verify(options, report, root_dir):
    etch_profile.resolve(options["profile"])
    delivery = etch_delivery.Delivery(report, options["output_root"])
    generation = delivery.resolve_pointer()
    if generation is None:
        report.log("no current generation under %s; nothing to verify" % delivery.root)
        return 0

    import json

    receipt_path = os.path.join(generation, "receipt.json")
    try:
        with open(receipt_path, encoding="utf-8") as handle:
            receipt = json.load(handle)
    except (OSError, ValueError) as error:
        report.failed("delivery/receipt")
        report.diagnostic(
            "delivery/receipt-unreadable", "the receipt could not be read: %s" % error, receipt_path
        )
        return 1
    report.passed("delivery/receipt")

    drifted = False
    for artifact in receipt.get("artifacts", []):
        path = os.path.join(generation, artifact["path"])
        actual = sha256_file(path) if os.path.isfile(path) else None
        if actual != artifact["sha256"]:
            drifted = True
            report.diagnostic(
                "delivery/artifact-drift",
                "%s no longer matches the hash recorded in the receipt" % path,
                path,
                expected=artifact["sha256"],
                actual=actual,
            )
        else:
            report.artifact(path, artifact["kind"], digest=actual)
    if drifted:
        report.failed("delivery/artifacts")
        return 1
    report.passed("delivery/artifacts")

    source = receipt.get("source", {})
    try:
        etch_delivery.confirm_hash(report, source.get("path", ""), source.get("sha256"), "verify")
    except etch_delivery.Conflict:
        return 3
    report.passed("delivery/handoff")
    return 0


def command_gc(options, report, root_dir):
    etch_profile.resolve(options["profile"])
    etch_delivery.collect(report, options["output_root"], delete=options["delete"])
    return 0


DISPATCH = {
    "validate": command_validate,
    "export": lambda o, r, d: command_export(o, r, d, commit_pointer=False),
    "deliver": lambda o, r, d: command_export(o, r, d, commit_pointer=True),
    "verify": command_verify,
    "gc": command_gc,
}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def install_signal_handlers():
    def handler(number, _frame):
        raise Interrupted("signal %d" % number)

    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(number, handler)
        except (ValueError, OSError):
            pass


def main(argv):
    root_dir = os.environ.get(
        "ETCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    report = Report(os.environ.get("ETCH_VERSION", "0.0.0"))
    install_signal_handlers()
    try:
        options = parse(argv)
        code = DISPATCH[options["command"]](options, report, root_dir)
    except UsageError as error:
        sys.stderr.write("etch: %s\n" % error)
        return 4
    except Interrupted as error:
        sys.stderr.write("etch: interrupted (%s); nothing was published\n" % error)
        return 130
    except etch_export.DependencyMissing:
        report.emit()
        return 5
    except Exception:  # noqa: BLE001 - report as an internal error, never as a usage error
        traceback.print_exc()
        try:
            report.failed("internal/unexpected-error")
            report.diagnostic(
                "internal/unexpected-error",
                "the tool itself failed; this is not a problem with the input",
                "(internal)",
            )
            report.emit()
        except Exception:  # noqa: BLE001 - best effort, per contracts/exit-codes.md
            pass
        return 6
    report.emit()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
