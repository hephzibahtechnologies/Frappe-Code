"""Virus/malware scanning for uploaded files.

Synchronous Frappe port of the MFT malware scanner
(Malwarescannerservice.py / Malwarescanintegration.py).

Every File inserted on the site is scanned before it is saved.
Engines, in priority order:
  1. ClamAV daemon via pyclamd (production engine, if installed/reachable)
  2. Pattern-match fallback (pure Python, always available)

Policy (fail-closed):
  CLEAN      -> allowed
  SKIPPED    -> allowed (file larger than scan_max_file_size)
  INFECTED   -> blocked + quarantined
  SUSPICIOUS -> blocked + quarantined (virus_scan_block_suspicious=0 to allow)
  ERROR      -> blocked (virus_scan_block_on_error=0 to allow)

Site config keys (site_config.json), all optional:
  virus_scan_enabled                 default 1
  virus_scan_max_file_size           default 104857600 (100 MB)
  virus_scan_block_suspicious        default 1
  virus_scan_block_on_error          default 1
  virus_scan_block_executables       default 1
  virus_scan_block_scripts           default 1   (shell/PHP/JS with wrong ext)
  virus_scan_block_suspicious_content default 1  (eval/exec/base64/powershell...)
  virus_scan_block_office_macros     default 1   (vbaProject.bin / remote links)
  virus_scan_block_pdf_active        default 1   (/JavaScript /Launch /EmbeddedFile)
  clamav_host / clamav_port / clamav_socket
"""

import hashlib
import json
import os
import shutil
import time

import frappe
from frappe import _
from frappe.utils import now_datetime

CLEAN = "CLEAN"
INFECTED = "INFECTED"
SUSPICIOUS = "SUSPICIOUS"
ERROR = "ERROR"
SKIPPED = "SKIPPED"

EICAR_SIGNATURE = (
	b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)
# Distinctive, escape-proof fragment of the EICAR string. Containers that escape
# special characters (PDF escapes ( ) \\, some XML encodings) break the full
# signature, but this fragment survives and is unique to the EICAR test file.
EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def _has_eicar(data):
	return EICAR_SIGNATURE in data or EICAR_MARKER in data

EXECUTABLE_SIGNATURES = {
	b"MZ": "PE (Windows) executable",
	b"\x7fELF": "ELF (Linux) executable",
}

# Heuristic signatures (expanded from the MFT scanner). Each maps a leading
# magic to (description, extensions where that content is legitimately expected).
SCRIPT_SIGNATURES = {
	b"#!/bin/":  ("Shell script", {".sh", ".bash", ".zsh"}),
	b"#! /bin/": ("Shell script", {".sh", ".bash", ".zsh"}),
	b"<?php":    ("PHP script", {".php"}),
	b"<script":  ("Inline script / HTML", {".html", ".htm", ".js"}),
}

# Byte substrings common in droppers, webshells and macro payloads.
SUSPICIOUS_CONTENT_PATTERNS = [
	b"eval(", b"exec(", b"system(", b"shell_exec(", b"base64_decode(",
	b"powershell", b"cmd.exe", b"/bin/bash", b"WScript.Shell",
	b"CreateObject(", b"Auto_Open", b"AutoOpen", b"Document_Open",
]

# OOXML (zip-based) Office documents.
OFFICE_ZIP_EXTS = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm",
                   ".dotm", ".xltm", ".potm"}
# Strong indicators of active/executable content inside a PDF.
PDF_STRONG_MARKERS = [b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile"]


def _conf(key, default):
	value = frappe.conf.get(key)
	return default if value is None else value


def _logger():
	import logging

	log = frappe.logger("virus_scan", allow_site=True)
	log.setLevel(logging.INFO)
	return log


def scan_file_before_insert(doc, method=None):
	"""doc_events hook: File.before_insert. Blocks infected uploads."""
	if not int(_conf("virus_scan_enabled", 1)):
		return
	if doc.is_folder or (doc.file_url or "").startswith("http"):
		return

	try:
		content = _get_file_content(doc)
	except _ContentUnreadable as e:
		# Fail closed: if the bytes cannot be read they cannot be certified
		# clean. Honor the block-on-error policy rather than saving unscanned.
		_logger().error(f"virus_scan could not read content of {doc.file_name}: {e}")
		if int(_conf("virus_scan_block_on_error", 1)):
			frappe.throw(
				_("File {0} could not be read for virus scanning and was blocked for safety.").format(
					frappe.bold(doc.file_name)
				),
				title=_("Virus Scan Failed"),
			)
		return

	# Genuinely empty file (0 bytes) — nothing to scan.
	if not content:
		return

	if len(content) > int(_conf("virus_scan_max_file_size", 100 * 1024 * 1024)):
		_logger().info(f"virus_scan SKIPPED (too large): {doc.file_name} ({len(content)} bytes)")
		return

	started = time.perf_counter()
	result, engine, threats, error = _scan_bytes(content, doc.file_name or "")
	duration = time.perf_counter() - started
	file_hash = hashlib.sha256(content).hexdigest()

	_logger().info(
		f"virus_scan {result} file={doc.file_name} engine={engine} "
		f"hash={file_hash} threats={threats} duration={duration:.3f}s"
	)

	block = (
		result == INFECTED
		or (result == SUSPICIOUS and int(_conf("virus_scan_block_suspicious", 1)))
		or (result == ERROR and int(_conf("virus_scan_block_on_error", 1)))
	)
	if not block:
		return

	report = {
		"file_name": doc.file_name,
		"file_size": len(content),
		"file_hash": file_hash,
		"scan_result": result,
		"scan_engine": engine,
		"threats_found": threats,
		"error_message": error,
		"scan_duration": round(duration, 3),
		"scan_timestamp": str(now_datetime()),
		"uploaded_by": frappe.session.user,
		"attached_to": f"{doc.attached_to_doctype or ''}/{doc.attached_to_name or ''}",
	}

	# Quarantine (filesystem) and log (file logger) both survive the rollback
	# that frappe.throw triggers below. The DMS Audit Log entry is written from
	# a background job so it persists independently of this aborted transaction.
	if result in (INFECTED, SUSPICIOUS):
		_quarantine(doc, content, report)

	_record_blocked_upload(doc, report)

	if result == ERROR:
		message = _("File {0} could not be virus-scanned and was blocked for safety: {1}").format(
			frappe.bold(doc.file_name), error
		)
	else:
		message = _("Upload blocked: file {0} failed the virus scan ({1}). Threats: {2}").format(
			frappe.bold(doc.file_name), result, ", ".join(threats) or _("unknown")
		)
	frappe.throw(message, title=_("Virus Scan Failed"))


class _ContentUnreadable(Exception):
	"""Raised when the uploaded file's bytes cannot be read at all (distinct
	from a genuinely empty file), so the caller can fail closed."""


def _get_file_content(doc):
	"""Return uploaded bytes from the File doc (memory or disk).

	Returns b"" for a genuinely empty file; raises _ContentUnreadable if the
	content cannot be read (so scanning fails closed instead of open)."""
	content = getattr(doc, "content", None)
	if content is None or content == "":
		try:
			content = doc.get_content()
		except Exception as e:
			raise _ContentUnreadable(str(e))
	if isinstance(content, str):
		content = content.encode("utf-8", errors="ignore")
	return content or b""


def _scan_bytes(content, file_name):
	"""Run the best available engine. Returns (result, engine, threats, error)."""
	clamd = None
	try:
		clamd = _get_clamd()
		if clamd:
			return _scan_with_clamav(clamd, content)
	except Exception as e:
		if int(_conf("virus_scan_block_on_error", 1)):
			return ERROR, "clamav", [], str(e)
		_logger().warning(f"virus_scan ClamAV error, falling back to pattern-match: {e}")

	# ClamAV is unavailable/unreachable. If this deployment requires it, fail
	# closed instead of silently downgrading to the weak pattern-match fallback
	# (which only detects EICAR + executable magic bytes — real malware passes).
	if clamd is None and int(_conf("virus_scan_require_clamav", 0)):
		return ERROR, "clamav", [], "ClamAV engine required but unavailable/unreachable"

	return _scan_with_pattern_match(content, file_name)


def _get_clamd():
	"""Connect to a ClamAV daemon if pyclamd is installed and clamd responds."""
	try:
		import pyclamd
	except ImportError:
		return None

	socket_path = _conf("clamav_socket", "/var/run/clamav/clamd.ctl")
	if socket_path and os.path.exists(socket_path):
		cd = pyclamd.ClamdUnixSocket(socket_path)
		if cd.ping():
			return cd

	host = _conf("clamav_host", None)
	if host:
		cd = pyclamd.ClamdNetworkSocket(host, int(_conf("clamav_port", 3310)))
		if cd.ping():
			return cd
	return None


def _scan_with_clamav(clamd, content):
	scan_result = clamd.scan_stream(content)
	if scan_result is None:
		return CLEAN, "clamav", [], None
	threats = [v[1] for v in scan_result.values()]
	return INFECTED, "clamav", threats, None


def _file_ext(file_name):
	return os.path.splitext(file_name or "")[1].lower()


_ARCHIVE_EXTS = (".zip", ".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm",
                 ".jar", ".7z", ".rar", ".gz", ".apk")
_ZIP_TEXT_SCAN_CAP = 10 * 1024 * 1024  # cap total decompressed bytes scanned


def _scan_zip_container(content, file_name):
	"""Open a zip / OOXML file and:
	  1) detect VBA macros (vbaProject.bin) and remote-template / external links,
	  2) DECOMPRESS the parts and scan their text for EICAR + suspicious patterns.
	A raw-byte scan cannot see inside a compressed container, so a signature
	hidden inside a .docx/.xlsx/.zip is only found by decompressing first.
	Returns (result, threats)."""
	import io
	import zipfile

	threats = []
	result = CLEAN
	try:
		with zipfile.ZipFile(io.BytesIO(content)) as z:
			names = z.namelist()

			if int(_conf("virus_scan_block_office_macros", 1)):
				if any(n.endswith("vbaProject.bin") for n in names):
					threats.append(f"Embedded VBA macro (vbaProject.bin) in Office file: {file_name}")
					result = SUSPICIOUS
				for n in names:
					if not n.endswith(".rels"):
						continue
					try:
						rel = z.read(n)
					except Exception:
						continue
					# Only remote-template injection is a real threat: an ordinary
					# hyperlink in the document body is ALSO TargetMode="External"
					# with an http(s) target -- that's simply how Word stores any
					# clickable link, and flagging it made virtually every RFP/
					# report with a citation or website link a false positive.
					# The attack this guards against specifically swaps the
					# document's *template* relationship (word/_rels/settings.xml
					# .rels, relationship type ".../attachedTemplate") for a
					# remote .dotm that can carry macros -- so only that
					# relationship type is a threat signal.
					if b"/attachedTemplate" in rel and b'TargetMode="External"' in rel and (
						b"http://" in rel or b"https://" in rel
					):
						threats.append(f"Remote template injection in Office relationships: {file_name}")
						result = SUSPICIOUS
						break

			# Decompress and concatenate part contents (bounded; skip nested
			# archives and oversized entries to avoid decompression bombs).
			blob = bytearray()
			for info in z.infolist():
				if info.is_dir() or info.file_size > _ZIP_TEXT_SCAN_CAP:
					continue
				if info.filename.lower().endswith(_ARCHIVE_EXTS):
					continue
				try:
					blob.extend(z.read(info.filename))
				except Exception:
					continue
				if len(blob) >= _ZIP_TEXT_SCAN_CAP:
					break
			blob = bytes(blob)

			# EICAR hidden inside the document is definitive.
			if _has_eicar(blob):
				return INFECTED, [f"EICAR-Test-Signature (inside {file_name})"]

			if int(_conf("virus_scan_block_suspicious_content", 1)):
				hits = [p.decode("ascii", "ignore") for p in SUSPICIOUS_CONTENT_PATTERNS if p in blob]
				if hits:
					threats.append(f"Suspicious content inside document {hits}: {file_name}")
					if result == CLEAN:
						result = SUSPICIOUS
	except zipfile.BadZipFile:
		return CLEAN, []  # not actually a zip/OOXML file
	except Exception:
		return CLEAN, []
	return result, threats


def _inflate_pdf_streams(content, cap=_ZIP_TEXT_SCAN_CAP):
	"""Decompress the FlateDecode `stream ... endstream` blocks of a PDF so the
	decompressed text can be scanned (a raw scan can't see inside them).
	Bounded to `cap` bytes; non-Flate/failed streams are skipped."""
	import re
	import zlib

	blob = bytearray()
	for m in re.finditer(rb"stream\r?\n", content):
		start = m.end()
		end = content.find(b"endstream", start)
		if end == -1:
			continue
		raw = content[start:end].rstrip(b"\r\n")
		try:
			data = zlib.decompress(raw)
		except Exception:
			continue
		blob.extend(data)
		if len(blob) >= cap:
			break
	return bytes(blob[:cap])


def _scan_pdf_document(content, file_name):
	"""Flag active content (JavaScript/launch/embedded) AND scan the decompressed
	PDF streams for EICAR + suspicious patterns. Returns (result, threats)."""
	threats = []
	result = CLEAN

	found = [m.decode() for m in PDF_STRONG_MARKERS if m in content]
	if found:
		# /OpenAction on its own is common/benign, so only surface it for context.
		if b"/OpenAction" in content:
			found.append("/OpenAction")
		threats.append(f"Active content in PDF ({', '.join(sorted(set(found)))}): {file_name}")
		result = SUSPICIOUS

	blob = _inflate_pdf_streams(content)
	if _has_eicar(blob):
		return INFECTED, [f"EICAR-Test-Signature (inside PDF stream): {file_name}"]

	if int(_conf("virus_scan_block_suspicious_content", 1)):
		hits = [p.decode("ascii", "ignore") for p in SUSPICIOUS_CONTENT_PATTERNS if p in blob]
		if hits:
			threats.append(f"Suspicious content inside PDF {hits}: {file_name}")
			if result == CLEAN:
				result = SUSPICIOUS

	return result, threats


def _scan_with_pattern_match(content, file_name):
	"""Pure-Python heuristic scan (no external engine). Expanded from the MFT
	scanner: EICAR + executables + scripts + suspicious content, plus
	document-aware checks for Office macros and PDF active content."""
	threats = []
	result = CLEAN
	ext = _file_ext(file_name)

	# 1) EICAR test signature anywhere in the raw bytes -> INFECTED (definitive).
	if _has_eicar(content):
		return INFECTED, "pattern_match", ["EICAR-Test-Signature"], None

	# 2) Raw executables (magic bytes).
	if int(_conf("virus_scan_block_executables", 1)):
		for signature, description in EXECUTABLE_SIGNATURES.items():
			if content.startswith(signature):
				threats.append(f"{description} content in upload: {file_name}")
				result = SUSPICIOUS

	# 3) Script content carried under an unexpected extension.
	if int(_conf("virus_scan_block_scripts", 1)):
		head = content[:64].lstrip()
		for sig, (desc, ok_exts) in SCRIPT_SIGNATURES.items():
			if head.startswith(sig) and ext not in ok_exts:
				threats.append(f"{desc} content with unexpected extension '{ext or 'none'}': {file_name}")
				result = SUSPICIOUS

	# 4) Zip / Office container: macros, remote links, and a DECOMPRESSED scan of
	#    the parts (catches EICAR / patterns hidden inside the compression).
	if content[:2] == b"PK":
		zres, zthreats = _scan_zip_container(content, file_name)
		if zres == INFECTED:
			return INFECTED, "pattern_match", zthreats, None
		if zres == SUSPICIOUS:
			threats.extend(zthreats)
			result = SUSPICIOUS

	# 5) PDF: active content + decompressed-stream scan (EICAR / patterns inside).
	if int(_conf("virus_scan_block_pdf_active", 1)) and content[:5] == b"%PDF-":
		pres, pthreats = _scan_pdf_document(content, file_name)
		if pres == INFECTED:
			return INFECTED, "pattern_match", pthreats, None
		if pres == SUSPICIOUS:
			threats.extend(pthreats)
			result = SUSPICIOUS

	# 6) Suspicious content substrings (bounded window to limit cost/false positives).
	if int(_conf("virus_scan_block_suspicious_content", 1)):
		window = content[:1_000_000]
		hits = [p.decode("ascii", "ignore") for p in SUSPICIOUS_CONTENT_PATTERNS if p in window]
		if hits:
			threats.append(f"Suspicious content pattern(s) {hits}: {file_name}")
			if result == CLEAN:
				result = SUSPICIOUS

	return result, "pattern_match", threats, None


def _quarantine(doc, content, report):
	"""Copy blocked file + JSON report into the site's private quarantine folder."""
	try:
		quarantine_dir = frappe.get_site_path("private", "quarantine")
		os.makedirs(quarantine_dir, exist_ok=True)

		safe_name = "".join(
			c for c in (doc.file_name or "unnamed") if c.isalnum() or c in "._-"
		)[:100]
		stamp = now_datetime().strftime("%Y%m%d_%H%M%S")
		base = os.path.join(quarantine_dir, f"{stamp}_{report['file_hash'][:16]}_{safe_name}")

		with open(base, "wb") as f:
			f.write(content)
		with open(base + ".json", "w") as f:
			json.dump(report, f, indent=2)

		report["quarantine_path"] = base
		_logger().warning(f"virus_scan quarantined blocked file to {base}")
	except Exception:
		_logger().error(f"virus_scan failed to quarantine {doc.file_name}", exc_info=True)


def _record_blocked_upload(doc, report):
	"""Record the blocked upload.

	The file logger and quarantine JSON survive the rollback that frappe.throw
	triggers. The DMS Audit Log row is enqueued as a background job so it is
	written in its own transaction and is not rolled back with the upload.
	"""
	_logger().warning(f"virus_scan BLOCKED upload: {json.dumps(report)}")

	if (
		doc.attached_to_doctype == "Document Library"
		and doc.attached_to_name
		and frappe.db.exists("Document Library", doc.attached_to_name)
	):
		try:
			frappe.enqueue(
				"quality_dms.dms.virus_scan.write_block_audit_log",
				queue="short",
				enqueue_after_commit=False,
				document=doc.attached_to_name,
				action=f"Upload Blocked - Virus Scan {report['scan_result']}",
				user=frappe.session.user,
			)
		except Exception:
			_logger().error("virus_scan failed to enqueue audit log entry", exc_info=True)


def write_block_audit_log(document, action, user):
	"""Background job: persist a DMS Audit Log entry for a blocked upload."""
	frappe.get_doc(
		{
			"doctype": "DMS Audit Log",
			"document": document,
			"action": action,
			"user": user,
			"timestamp": now_datetime(),
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
