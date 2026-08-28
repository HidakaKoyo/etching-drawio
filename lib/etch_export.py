"""draw.io Desktop resolution, export, and verification of what it produced.

Output verification never shells out to sips (macOS only, and it proves little).
PNG is walked chunk by chunk with CRC checks and an IDAT inflate cross-checked
against IHDR; SVG and PDF are checked with the standard library. xmllint and
file stay optional (contracts/environment.md §5).
"""

import os
import re
import shutil
import signal
import struct
import subprocess
import xml.etree.ElementTree as ElementTree
import zlib

EXPORT_TIMEOUT_SECONDS = 120
VERSION_TIMEOUT_SECONDS = 20
VERSION_LINE = re.compile(r"^\d+(\.\d+)+$")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

MACOS_BUNDLES = (
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    os.path.expanduser("~/Applications/draw.io.app/Contents/MacOS/draw.io"),
)
LINUX_PATHS = (
    "/usr/bin/drawio",
    "/usr/local/bin/drawio",
    "/opt/drawio/drawio",
    "/snap/bin/drawio",
)


class DependencyMissing(Exception):
    """A required external dependency is absent (exit 5)."""


class ExportFailed(Exception):
    """draw.io ran but the result is unusable (exit 2)."""


def resolve_drawio(report):
    """DRAWIO_CMD, then PATH, then the macOS bundle, then the Linux defaults.

    A DRAWIO_CMD that is set but not executable is an error, not a reason to
    fall back: an explicit choice is never silently ignored.
    """
    explicit = os.environ.get("DRAWIO_CMD")
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit
        report.failed("dependency/drawio")
        report.diagnostic(
            "dependency/drawio",
            "DRAWIO_CMD points at %s, which is not an executable file; "
            "an explicit setting is never silently replaced by a PATH lookup" % explicit,
            "(environment)",
            actual=explicit,
        )
        raise DependencyMissing()

    found = shutil.which("drawio")
    if found is None:
        for candidate in MACOS_BUNDLES + LINUX_PATHS:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found = candidate
                break
    if found is None:
        report.failed("dependency/drawio")
        report.diagnostic(
            "dependency/drawio",
            "draw.io Desktop was not found. Set DRAWIO_CMD to its executable, "
            "or install it so that `drawio` is on PATH.",
            "(environment)",
        )
        raise DependencyMissing()
    return found


def drawio_version(command):
    try:
        completed = subprocess.run(
            [command, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = completed.stdout.decode("utf-8", "replace")
    # Electron writes its own noise to stderr before answering - on a Linux CI
    # runner the first line is a dbus complaint. Taking line one would put that
    # string in the receipt as the version, so pick the line that is a version.
    for line in text.splitlines():
        candidate = line.strip()
        if VERSION_LINE.match(candidate):
            return candidate
    return "unknown"


def build_argv(command, source, destination, fmt, page, scale, embed_xml):
    argv = [command, "--disable-update", "-x", "-f", fmt, "-p", str(page)]
    if fmt == "png":
        argv += ["-s", str(scale)]
    if embed_xml:
        argv.append("-e")
    argv += ["-o", destination, source]
    return argv


def run_export(report, argv, log_path):
    """Run draw.io in its own session so a timeout can take the whole group."""
    with open(log_path, "wb") as log:
        try:
            process = subprocess.Popen(
                argv, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
        except OSError as error:
            report.failed("export/run")
            report.diagnostic(
                "export/failed", "draw.io could not be started: %s" % error, argv[0]
            )
            raise ExportFailed()
        try:
            status = process.wait(timeout=EXPORT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            terminate_group(process)
            report.failed("export/run")
            report.diagnostic(
                "export/timeout",
                "draw.io did not finish within %d seconds" % EXPORT_TIMEOUT_SECONDS,
                argv[0],
            )
            raise ExportFailed()
        except BaseException:
            # A signal reached us while draw.io was running. It has its own
            # session, so it would otherwise outlive this process.
            terminate_group(process)
            raise

    if status != 0:
        report.failed("export/run")
        report.diagnostic(
            "export/failed", "draw.io exited with status %d" % status, argv[0], actual=status
        )
        report.log("draw.io log (first lines):")
        for line in head_lines(log_path, 8):
            report.log("  %s" % line)
        raise ExportFailed()
    report.passed("export/run")


def terminate_group(process):
    for send in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, send)
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def head_lines(path, count):
    try:
        with open(path, "rb") as handle:
            text = handle.read(65536).decode("utf-8", "replace")
    except OSError:
        return []
    return text.splitlines()[:count]


# ---------------------------------------------------------------------------
# output verification
# ---------------------------------------------------------------------------


def verify_output(report, path, fmt, embed_xml=False):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        report.failed("export/output-present")
        report.diagnostic(
            "export/output-missing", "draw.io produced no output, or an empty file", path
        )
        raise ExportFailed()
    report.passed("export/output-present")

    checker = {"svg": verify_svg, "png": verify_png, "pdf": verify_pdf}[fmt]
    problem = checker(path, embed_xml)
    if problem is not None:
        code, message = problem
        report.failed("export/%s-valid" % fmt)
        report.diagnostic(code, message, path)
        raise ExportFailed()
    report.passed("export/%s-valid" % fmt)


def verify_svg(path, embed_xml):
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError) as error:
        return "export/svg-not-well-formed", "the exported SVG is not well-formed: %s" % error
    if root.tag.rsplit("}", 1)[-1] != "svg":
        return (
            "export/svg-root",
            "the exported file's root element is <%s>, expected <svg>" % root.tag,
        )
    if embed_xml and root.get("content") is None:
        return (
            "export/svg-missing-content",
            "--embed-xml was requested but the SVG carries no content attribute",
        )
    return None


def verify_pdf(path, _embed_xml):
    with open(path, "rb") as handle:
        if handle.read(5) != b"%PDF-":
            return "export/pdf-magic", "the exported file does not start with the PDF magic"
    return None


def verify_png(path, _embed_xml):
    """Walk every chunk, verify each CRC, then inflate IDAT and compare to IHDR."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != PNG_SIGNATURE:
        return "export/png-signature", "the exported file does not carry the PNG signature"

    position = 8
    header = None
    compressed = []
    saw_end = False
    while position < len(data):
        if position + 8 > len(data):
            return "export/png-truncated", "the PNG ends inside a chunk header"
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        end = position + 8 + length
        if end + 4 > len(data):
            return "export/png-truncated", "chunk %r claims more bytes than the file holds" % kind
        payload = data[position + 8 : end]
        stored = struct.unpack(">I", data[end : end + 4])[0]
        if stored != zlib.crc32(kind + payload) & 0xFFFFFFFF:
            return "export/png-crc", "chunk %r fails its CRC check" % kind
        if kind == b"IHDR":
            if length != 13:
                return "export/png-ihdr", "IHDR is %d bytes, expected 13" % length
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            saw_end = True
        position = end + 4

    if header is None:
        return "export/png-ihdr", "the PNG carries no IHDR chunk"
    if not saw_end:
        return "export/png-truncated", "the PNG carries no IEND chunk"
    if not compressed:
        return "export/png-idat", "the PNG carries no IDAT chunk"

    width, height, depth, colour, compression, filtering, interlace = header
    if width == 0 or height == 0:
        return "export/png-ihdr", "IHDR declares a zero dimension (%dx%d)" % (width, height)
    if compression != 0 or filtering != 0:
        return "export/png-ihdr", "IHDR declares an unknown compression or filter method"
    if colour not in PNG_CHANNELS:
        return "export/png-ihdr", "IHDR declares an unknown colour type %d" % colour

    try:
        raw = zlib.decompress(b"".join(compressed))
    except zlib.error as error:
        return "export/png-idat", "the IDAT stream does not inflate: %s" % error

    if interlace == 0:
        row_bytes = (width * depth * PNG_CHANNELS[colour] + 7) // 8
        expected = height * (row_bytes + 1)
        if len(raw) != expected:
            return (
                "export/png-idat",
                "the inflated image is %d bytes but IHDR (%dx%d) implies %d"
                % (len(raw), width, height, expected),
            )
    elif not raw:
        return "export/png-idat", "the interlaced IDAT stream inflates to nothing"
    return None
