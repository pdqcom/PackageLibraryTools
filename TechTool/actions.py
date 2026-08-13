import csv
import getpass
import html
import os
import re
import shutil
import tempfile
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import ai
import json
import time
import textwrap
import fnmatch
from difflib import SequenceMatcher
from datetime import datetime, timezone
from tkinter import filedialog, messagebox
from urllib.parse import urlparse


# ==========================================
# Constants
# ==========================================

VIRUSTOTAL_GUI_PREFIX = "https://www.virustotal.com/gui/"
NOTION_API_KEY_ENV = "Notion_API_Key"
NOTION_DATABASE_ID = "314964a5c89680c89d2fd32ae75a21ec"
NOTION_API_URL = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
NOTION_CACHE_PATH = r"C:\ProgramData\TechTool\troubleshooting_cache.json"
NOTION_CACHE_MAX_AGE_SECONDS = 60 * 60 * 24

# ==========================================
# Troubleshooting Database Helpers
# ==========================================

def load_troubleshooting_cache():
    if not os.path.isfile(NOTION_CACHE_PATH):
        return []

    try:
        with open(NOTION_CACHE_PATH, "r", encoding="utf-8", errors="replace") as file:
            data = json.load(file)

        return data.get("errors", [])

    except Exception:
        return []


def troubleshooting_cache_is_stale():
    if not os.path.isfile(NOTION_CACHE_PATH):
        return True

    try:
        age_seconds = time.time() - os.path.getmtime(NOTION_CACHE_PATH)
        return age_seconds >= NOTION_CACHE_MAX_AGE_SECONDS

    except Exception:
        return True


def refresh_troubleshooting_cache():
    api_key = os.getenv(NOTION_API_KEY_ENV)
    if not api_key:
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    request = urllib.request.Request(
        NOTION_API_URL,
        data=b"{}",
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

        errors = []

        for item in result.get("results", []):
            properties = item.get("properties", {})

            error_title = properties.get("Error", {}).get("title", [])
            troubleshooting_text = properties.get("Troubleshooting Step", {}).get("rich_text", [])

            error_value = "".join(part.get("plain_text", "") for part in error_title).strip()
            troubleshooting_value = "".join(part.get("plain_text", "") for part in troubleshooting_text).strip()

            if not error_value and not troubleshooting_value:
                continue

            errors.append({
                "error": error_value,
                "troubleshooting_step": troubleshooting_value
            })

        os.makedirs(os.path.dirname(NOTION_CACHE_PATH), exist_ok=True)

        cache_data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "errors": errors
        }

        with open(NOTION_CACHE_PATH, "w", encoding="utf-8", errors="replace") as file:
            json.dump(cache_data, file, indent=2)

        return True

    except Exception:
        return False

def troubleshooting_error_matches(error_text, report_text):
    error_text = (error_text or "").strip().lower()
    report_text = (report_text or "").lower()

    if not error_text:
        return False

    if error_text in report_text:
        return True

    if "*" in error_text or "?" in error_text:
        for line in report_text.splitlines():
            if fnmatch.fnmatch(line.strip(), f"*{error_text}*"):
                return True

    normalized_error = re.sub(r"\s+", " ", error_text)
    normalized_lines = [re.sub(r"\s+", " ", line.strip()) for line in report_text.splitlines() if line.strip()]

    for line in normalized_lines:
        if SequenceMatcher(None, normalized_error, line).ratio() >= 0.80:
            return True

    return False

# ==========================================
# Action Helpers
# ==========================================

def open_path(path):
    if not path:
        messagebox.showwarning("Missing Path", "No path was found.")
        return

    if not os.path.exists(path):
        messagebox.showwarning("Path Not Found", f"Path does not exist:\n{path}")
        return

    os.startfile(path)



# ==========================================
# Audit Log Helpers
# ==========================================

def get_audit_log_path(report_folder):
    if not report_folder: return ""
    return os.path.join(report_folder, "audit.report")


def append_tech_tool_audit_log(report_folder, action=None, target_path=None, current_user=None, comment_text=None):
    audit_log_path = get_audit_log_path(report_folder)
    if not audit_log_path: raise Exception("Unable to determine where audit.report should be created.")

    timestamp = datetime.now(timezone.utc).strftime("%#m/%#d/%Y %#I:%M:%S %p UTC")
    current_user = current_user or getpass.getuser()

    lines = [
        "----- Begin Tech Tool Action -----",
        f"TECH_Owner;PASSED;{current_user};{timestamp}",
    ]

    if comment_text is not None: lines.append(f"TECH_Comment;PASSED;PASSED;{comment_text}")
    else: lines.append(f"TECH_Work;PASSED;{action};{target_path}")

    lines.append("-----  End Tech Tool Action  -----")
    entry = "\n".join(lines)

    def append_entry(report_path, create_if_missing=False):
        if not report_path: return
        if not create_if_missing and not os.path.isfile(report_path): return
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        existing_text = ""
        if os.path.isfile(report_path):
            with open(report_path, "r", encoding="utf-8", errors="replace") as file:
                existing_text = file.read().strip()

        with open(report_path, "w", encoding="utf-8", errors="replace") as file:
            if existing_text: file.write(existing_text + "\n\n" + entry + "\n")
            else: file.write(entry + "\n")

    append_entry(audit_log_path, create_if_missing=True)

    #append to qa.report as well for record keeping
    qa_report_path = os.path.join(os.path.dirname(audit_log_path), "QA.report")
    append_entry(qa_report_path, create_if_missing=False)


# ==========================================
# Universal Actions
# ==========================================

def get_version_exception_path(app_path):
    if not app_path: return ""
    return os.path.join(app_path, "Version.exception")


def load_version_exception(app_path):
    exception_path = get_version_exception_path(app_path)

    if exception_path and os.path.isfile(exception_path):
        with open(exception_path, "r", encoding="utf-8", errors="replace") as file: return file.read(), True

    default_contents = """# Exception Summary:

$version = "%VERSION%"

### Do things to adjust the Deploy version to match the Inventory version ###

return $version
"""

    return default_contents, False


def save_version_exception(app_path, exception_contents, report_folder=None, current_user=None):
    if not app_path or not os.path.isdir(app_path):
        messagebox.showwarning("Missing Package Folder", "No package folder was found.")
        return False

    exception_contents = exception_contents or ""

    if "%VERSION%" not in exception_contents:
        return False

    exception_path = get_version_exception_path(app_path)

    with open(exception_path, "w", encoding="utf-8", errors="replace") as file: file.write(exception_contents)

    append_tech_tool_audit_log(report_folder=report_folder, action="SaveVersionException", target_path=exception_path, current_user=current_user)
    return True


def generate_inventory_version_exception(version_folder, deploy_version):
    if not version_folder or not os.path.isdir(version_folder):
        raise Exception("No version folder was found.")

    qa_report_path = next((entry.path for entry in os.scandir(version_folder) if entry.is_file() and entry.name.lower() == "qa.report"), "")

    if not qa_report_path:
        raise Exception("QA.report was not found in the version folder.")

    with open(qa_report_path, "r", encoding="utf-8", errors="replace") as file: qa_report_contents = file.read()

    inventory_version = get_inventory_version_from_qa_report(qa_report_path)

    if not inventory_version:
        raise Exception("The inventory version could not be found in QA.report.")

    instructions = """You create PowerShell Version.exception scripts for software packages.

Return only the PowerShell script. Do not use Markdown code fences or include an explanation outside the script.

The script must:
- Keep the placeholder '%VERSION%' in the script.
- Start with $preVersion = "%VERSION%".
- Transform $preVersion so it matches the supplied inventory version format.
- Store the final result in $newVersion.
- End with return $newVersion.
- Include a short # Exception Summary comment explaining the transformation.
- Use only the information supplied in the request and QA report.
- Keep the script as simple and readable as possible.
- Do not hardcode the current deploy version as the returned value.
- You may use '%InvAppName%' or '%InvVersion%' only when they are genuinely needed."""

    prompt = f"""Create a Version.exception PowerShell script.

Deploy version:
{deploy_version}

Inventory version:
{inventory_version}

Determine the smallest reliable transformation needed to convert the deploy version format into the inventory version format."""

    return ai.ask_ai(prompt=prompt, instructions=instructions, context=qa_report_contents)

def wrap_report_text(text, width=80):
    lines = []

    for line in (text or "").splitlines():
        stripped_line = line.strip()

        if not stripped_line:
            lines.append("")
            continue

        lines.append(textwrap.fill(stripped_line, width=width, subsequent_indent="   " if re.match(r"^\d+[\.\)]\s+", stripped_line) else ""))

    return "\n".join(lines)

def generate_ai_analysis(version_folder, app_name, version, status, reason="", failed_step="", extra_context="", troubleshooting_errors=None):
    if not version_folder or not os.path.isdir(version_folder):
        raise Exception("No version folder was found.")

    report_files = [
        entry
        for entry in os.scandir(version_folder)
        if entry.is_file()
        and entry.name.lower().endswith(".report")
        and entry.name.lower() != "aianalyzed.report"
    ]

    if not report_files:
        raise Exception("No report files were found to analyze.")

    report_files.sort(key=lambda entry: entry.name.lower())

    report_sections = []

    for entry in report_files:
        try:
            with open(entry.path, "r", encoding="utf-8", errors="replace") as file:
                contents = file.read().strip()
        except Exception as error:
            contents = f"[Unable to read report: {error}]"

        report_sections.append(f"--- {entry.name} ---\n{contents}")

    report_text_for_matching = "\n".join(report_sections)

    matched_troubleshooting_sections = []
    other_troubleshooting_sections = []

    for item in troubleshooting_errors or []:
        error_text = (item.get("error") or "").strip()
        step_text = (item.get("troubleshooting_step") or "").strip()

        if not error_text and not step_text:
            continue

        entry = f"Documented Error: {error_text}\nDocumented Procedure:\n{step_text}"

        if troubleshooting_error_matches(error_text, report_text_for_matching):
            matched_troubleshooting_sections.append(entry)
        else:
            other_troubleshooting_sections.append(entry)

    instructions = """You are a software package troubleshooting expert.

Review the supplied package information, report files, matched troubleshooting procedures, and additional troubleshooting reference data.

Determine:
- Reason: what happened.
- Cause: the most likely root cause. Explain meaningful patterns such as operating system, device type, server/client differences, repeated failures, or other correlations when evidence exists.
- Fix: the most probable resolution. When multiple actions are required, return a numbered list with each step on its own line.
- Evidence: brief supporting information showing which documented troubleshooting knowledge was used.

The MATCHED DOCUMENTED TROUBLESHOOTING PROCEDURES section contains troubleshooting procedures whose documented error text matched the package reports using exact, wildcard, or fuzzy matching.

When one or more matched procedures are supplied:
- Treat the matched procedure as the primary troubleshooting playbook.
- Use the package reports to determine which condition or branch in the documented procedure applies.
- The Fix must begin with the applicable documented troubleshooting step.
- Follow the documented procedure in its intended order.
- Do not skip ahead to a later troubleshooting branch merely because it seems technically plausible.
- If the reports do not contain enough information to determine which documented branch applies, state what should be checked next instead of guessing.
- Additional recommendations may be included only after the applicable documented procedure.
- If a matched documented procedure exists, Evidence must name the matched documented error or fix and state that the documented troubleshooting procedure was used.
- Only reject a matched documented procedure when the package reports contain clear contradictory evidence. If rejected, briefly explain why in Evidence.

The ADDITIONAL TROUBLESHOOTING REFERENCE section contains other known troubleshooting information that did not directly match the reports. Use it only when relevant.

Formatting requirements:
- When Fix contains multiple steps, format them as a numbered list with each numbered step on its own line.
- Put a blank line before a numbered list when introductory text appears before it.
- Keep each numbered action as a separate step rather than combining multiple numbered actions into one paragraph.

General requirements:
- Be concise and evidence-based.
- Do not invent facts that are not supported by the supplied information.
- Clearly distinguish confirmed evidence from likely conclusions.
- Do not hardcode a current version number as a permanent fix unless the supplied documented procedure explicitly requires it.
- Prefer a documented troubleshooting procedure over a speculative fix when a match exists.
- Keep Evidence brief and generic. Do not repeat detailed report evidence unless it is necessary to understand the conclusion.
- Return only valid JSON.
- The JSON object must contain exactly these string properties: Reason, Cause, Fix, Evidence.
"""

    prompt = f"""Analyze this package failure.

PACKAGE
-------
App: {app_name}
Version: {version}
Status: {status}
Reason: {reason}
Failed Step: {failed_step}

EXTRA CONTEXT
-------------
{extra_context or "(none provided)"}

MATCHED DOCUMENTED TROUBLESHOOTING PROCEDURES
---------------------------------------------
{chr(10).join(matched_troubleshooting_sections) if matched_troubleshooting_sections else "(no matching documented procedure found)"}

ADDITIONAL TROUBLESHOOTING REFERENCE
------------------------------------
{chr(10).join(other_troubleshooting_sections) if other_troubleshooting_sections else "(none)"}

PACKAGE REPORTS
===============
{chr(10).join(report_sections)}
"""

    ai_response = ai.ask_ai(prompt=prompt, instructions=instructions)
    cleaned_response = ai_response.strip()

    if cleaned_response.startswith("```"):
        cleaned_response = re.sub(r"^```(?:json)?\s*", "", cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r"\s*```$", "", cleaned_response)

    try:
        result = json.loads(cleaned_response)
    except json.JSONDecodeError as error:
        raise Exception(f"AI returned an invalid analysis response: {error}")

    reason_result = str(result.get("Reason", "")).strip()
    cause_result = str(result.get("Cause", "")).strip()
    fix_result = str(result.get("Fix", "")).strip()
    evidence_result = str(result.get("Evidence", "")).strip()

    reason_result = wrap_report_text(reason_result)
    cause_result = wrap_report_text(cause_result)
    fix_result = wrap_report_text(fix_result)
    evidence_result = wrap_report_text(evidence_result)

    report_text = f"""AI Analysis
===========

Reason:
{reason_result}

Cause:
{cause_result}

Fix:
{fix_result}

Evidence:
{evidence_result}
"""

    output_path = os.path.join(version_folder, "AiAnalyzed.report")

    with open(output_path, "w", encoding="utf-8", errors="replace") as file:
        file.write(report_text)

    return output_path

def get_installer_download_defaults(version_folder):
    """
    Returns:
        download_url: Contents of PackageInstallerURL.txt, or blank.
        installer_location: Newest XML filename with .exe substituted.
    """
    if not version_folder or not os.path.isdir(version_folder):
        return "", ""

    url_file_path = os.path.join(version_folder, "PackageInstallerURL.txt")
    download_url = ""

    if os.path.isfile(url_file_path):
        try:
            with open(url_file_path, "r", encoding="utf-8", errors="replace") as file:
                download_url = file.read().strip()
        except Exception:
            download_url = ""

    xml_files = [entry for entry in os.scandir(version_folder) if entry.is_file() and entry.name.lower().endswith(".xml")]

    if not xml_files:
        return download_url, ""

    xml_files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)

    xml_basename = os.path.splitext(xml_files[0].name)[0]
    installer_location = os.path.join(version_folder, f"{xml_basename}.exe")

    return download_url, installer_location


def download_and_replace_installer(version_folder, source_mode, download_url, local_installer_path, installer_location, report_folder=None, current_user=None):
    if not version_folder or not os.path.isdir(version_folder):
        messagebox.showwarning("Missing Version Folder", "No version folder was found.")
        return False

    source_mode = (source_mode or "URL").strip()
    download_url = (download_url or "").strip()
    local_installer_path = (local_installer_path or "").strip().strip('"')
    installer_location = (installer_location or "").strip().strip('"')

    if not installer_location:
        messagebox.showwarning("Missing Location", "Enter the installer location.")
        return False

    if os.path.isabs(installer_location): destination_path = os.path.normpath(installer_location)
    else: destination_path = os.path.normpath(os.path.join(version_folder, installer_location))

    destination_folder = os.path.dirname(destination_path) or version_folder

    if not os.path.isdir(destination_folder):
        messagebox.showwarning("Destination Not Found", f"The destination folder does not exist:\n{destination_folder}")
        return False

    if source_mode == "Local":
        if not local_installer_path:
            messagebox.showwarning("Missing Installer", "Select a local installer.")
            return False

        if not os.path.isfile(local_installer_path):
            messagebox.showwarning("Installer Not Found", f"The selected installer does not exist:\n{local_installer_path}")
            return False

        if os.path.normcase(os.path.abspath(local_installer_path)) == os.path.normcase(os.path.abspath(destination_path)):
            messagebox.showwarning("Same File", "The selected installer is already the destination file.")
            return False

    else:
        if not download_url:
            messagebox.showwarning("Missing URL", "Enter an installer download URL.")
            return False

        parsed_url = urlparse(download_url)

        if parsed_url.scheme.lower() not in ("http", "https"):
            messagebox.showwarning("Invalid URL", "The installer URL must begin with http:// or https://.")
            return False

    url_file_path = os.path.join(version_folder, "PackageInstallerURL.txt")
    temporary_path = ""

    try:
        temporary_file = tempfile.NamedTemporaryFile(prefix="TechToolInstaller_", suffix=".replacement", dir=destination_folder, delete=False)
        temporary_path = temporary_file.name
        temporary_file.close()

        if source_mode == "Local": shutil.copy2(local_installer_path, temporary_path)
        else:
            request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"})

            with urllib.request.urlopen(request, timeout=120) as response:
                status_code = getattr(response, "status", 200)
                if status_code < 200 or status_code >= 300: raise Exception(f"Download returned HTTP status {status_code}.")
                with open(temporary_path, "wb") as output_file: shutil.copyfileobj(response, output_file)

        if not os.path.isfile(temporary_path): raise Exception("The temporary installer file was not created.")
        if os.path.getsize(temporary_path) <= 0: raise Exception("The installer file was empty.")

        os.replace(temporary_path, destination_path)
        temporary_path = ""

        if source_mode == "URL":
            with open(url_file_path, "w", encoding="utf-8", errors="replace") as file: file.write(download_url)
            audit_action = f"DownloadAndReplaceInstaller: {download_url}"
        else: audit_action = f"ReplaceInstallerFromLocal: {local_installer_path}"

        append_tech_tool_audit_log(report_folder=report_folder, action=audit_action, target_path=destination_path, current_user=current_user)
        return True

    finally:
        if temporary_path and os.path.isfile(temporary_path):
            try:
                os.remove(temporary_path)
            except Exception:
                pass

def copy_directory(source_path, report_folder, current_user=None):
    if not source_path:
        messagebox.showwarning("Missing Path", "No path was found.")
        return False

    if not os.path.isdir(source_path):
        messagebox.showwarning("Folder Not Found", f"Folder does not exist:\n{source_path}")
        return False

    destination_parent = filedialog.askdirectory(title="Select where to copy this folder")
    if not destination_parent: return False

    folder_name = os.path.basename(source_path.rstrip("\\/"))
    destination_path = os.path.join(destination_parent, folder_name)

    if os.path.exists(destination_path):
        messagebox.showwarning("Folder Already Exists", f"Destination already exists:\n{destination_path}")
        return False

    shutil.copytree(source_path, destination_path)

    append_tech_tool_audit_log(
        report_folder=report_folder,
        action="CopyDirectory",
        target_path=source_path,
        current_user=current_user
    )

    messagebox.showinfo("Copy Complete", f"Copied folder to:\n{destination_path}")
    return True


def replace_icon(app_path, report_folder, current_user=None):
    selected_file = filedialog.askopenfilename(
        title="Select replacement icon",
        initialdir=app_path,
        initialfile="icon.png",
        filetypes=[("PNG files", "*.png")]
    )

    if not selected_file: return False

    target_path = os.path.join(app_path, "icon.png")
    if not target_path:
        messagebox.showwarning("Missing Path", "No app path was found.")
        return False

    shutil.copy2(selected_file, target_path)

    append_tech_tool_audit_log(
        report_folder=report_folder,
        action="ReplaceIcon",
        target_path=selected_file,
        current_user=current_user
    )

    return True

def get_ready_pub_defaults(app_path, version_folder, fallback_version):
    inventory_variable = ""
    inventory_version = fallback_version or ""
    xml_path = ""

    if app_path and os.path.isdir(app_path):
        variable_files = [
            entry
            for entry in os.scandir(app_path)
            if entry.is_file()
            and entry.name.lower().startswith("appver")
            and entry.name.lower().endswith(".variable")
        ]

        variable_files.sort(key=lambda entry: entry.name.lower())

        if variable_files:
            inventory_variable = os.path.splitext(variable_files[0].name)[0]

    if version_folder and os.path.isdir(version_folder):
        qa_report_path = next(
            (
                entry.path
                for entry in os.scandir(version_folder)
                if entry.is_file() and entry.name.lower() == "qa.report"
            ),
            ""
        )

        scanned_version = get_inventory_version_from_qa_report(qa_report_path)
        if scanned_version: inventory_version = scanned_version

        xml_files = [entry for entry in os.scandir(version_folder) if entry.is_file() and entry.name.lower().endswith(".xml")]
        xml_files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)

        if xml_files: xml_path = xml_files[0].path

    return inventory_variable, inventory_version, xml_path


def get_inventory_version_from_qa_report(qa_report_path):
    if not qa_report_path or not os.path.isfile(qa_report_path):
        return ""

    expected_header = "ComputerName,Name,Version,InstallDate,RegistryHive"

    try:
        with open(qa_report_path, "r", encoding="utf-8", errors="replace") as file:
            lines = file.read().splitlines()

        for index, line in enumerate(lines):
            if line.strip().lstrip(">") != expected_header:
                continue

            data_line = next((candidate for candidate in lines[index + 1:] if candidate.strip()), "")
            if not data_line: return ""

            rows = list(csv.DictReader([expected_header, data_line]))
            if not rows: return ""

            return (rows[0].get("Version") or "").strip()

    except Exception:
        return ""

    return ""


def prepare_ready_pub(app_path, status_file, repo_path, app_name, inventory_variable, inventory_version, xml_path, version_folder, current_user=None):
    if not app_path or not os.path.isdir(app_path):
        messagebox.showwarning("Missing Package Folder", "No package folder was found.")
        return False

    if not status_file or not os.path.isfile(status_file):
        messagebox.showwarning("Missing Status File", "No existing status file was found.")
        return False

    if not repo_path or not os.path.isdir(repo_path):
        messagebox.showwarning("Missing Repository", f"The selected repository does not exist:\n{repo_path}")
        return False

    if not version_folder or not os.path.isdir(version_folder):
        messagebox.showwarning("Missing Version Folder", "No version folder was found.")
        return False

    app_name = (app_name or "").strip()
    inventory_variable = (inventory_variable or "").strip()
    inventory_version = (inventory_version or "").strip()
    xml_path = (xml_path or "").strip().strip('"')
    current_user = current_user or getpass.getuser()

    missing_fields = []

    if not app_name: missing_fields.append("App Name")
    if not inventory_variable: missing_fields.append("Inventory Variable")
    if not inventory_version: missing_fields.append("Inventory Version")
    if not xml_path: missing_fields.append("XML Path")

    if missing_fields:
        messagebox.showwarning("Missing Information", "Complete the following fields:\n\n" + "\n".join(missing_fields))
        return False

    if not os.path.isfile(xml_path):
        messagebox.showwarning("XML Not Found", f"The selected XML file does not exist:\n{xml_path}")
        return False

    new_status_file = os.path.join(app_path, "READY_Pub.status")

    if os.path.normcase(os.path.abspath(status_file)) == os.path.normcase(os.path.abspath(new_status_file)):
        messagebox.showwarning("Already READY_Pub", "This package is already set to READY_Pub.")
        return False

    if os.path.exists(new_status_file):
        messagebox.showwarning("Status File Exists", f"That status file already exists:\n{new_status_file}")
        return False

    upload_folder = os.path.join(repo_path, "Upload")
    is_new_package = os.path.isfile(os.path.join(app_path, "new.package"))

    if is_new_package: upload_folder = os.path.join(upload_folder, "OnHold_NOT_PUBED")

    if not os.path.isdir(upload_folder):
        messagebox.showwarning("Upload Folder Not Found", f"The upload folder does not exist:\n{upload_folder}")
        return False

    clean_app_name = re.sub(r"\s+", "", app_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    upload_filename = f"{clean_app_name}_{timestamp}_Firehose_Upload.txt"
    upload_path = os.path.join(upload_folder, upload_filename)
    review_path = os.path.join(version_folder, "PackageReview.html")
    review_created = False
    upload_created = False
    replaced_upload_files = {}

    upload_file_contents = [
        ["PackageName", "InventoryVariable", "InventoryVersion", "PackageXMLPath"],
        [app_name, inventory_variable, inventory_version, xml_path],
    ]

    try:
        temporary_upload = tempfile.NamedTemporaryFile(prefix="TechToolReadyPub_", suffix=".txt", dir=upload_folder, delete=False)
        temporary_upload_path = temporary_upload.name
        temporary_upload.close()

        try:
            with open(temporary_upload_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file, lineterminator="\n")
                writer.writerows(upload_file_contents)

            if not os.path.isfile(temporary_upload_path) or os.path.getsize(temporary_upload_path) <= 0:
                raise Exception("The upload file could not be generated.")

            if is_new_package:
                upload_pattern = re.compile(rf"^{re.escape(clean_app_name)}_\d{{14}}_Firehose_Upload\.txt$", re.IGNORECASE)

                for entry in os.scandir(upload_folder):
                    if not entry.is_file() or not upload_pattern.fullmatch(entry.name):
                        continue

                    with open(entry.path, "rb") as file:
                        replaced_upload_files[entry.path] = file.read()

                    os.remove(entry.path)

            os.replace(temporary_upload_path, upload_path)
            upload_created = True

        finally:
            if os.path.isfile(temporary_upload_path):
                os.remove(temporary_upload_path)

        if not os.path.isfile(upload_path):
            raise Exception(f"The upload file was not found after creation:\n{upload_path}")

        if not os.path.isfile(review_path):
            runtime = datetime.now(timezone.utc).strftime("%#m/%#d/%Y %#I:%M:%S %p UTC")

            review_contents = f"""<!DOCTYPE html>
<html>
<body>
<p>Technician changed status to READY_Pub before a HTML Review page was generated.</p>
<p>Technician: {html.escape(current_user)}<br>RunTime: {html.escape(runtime)}</p><hr>
<p>Audit Report:<br><iframe src="audit.report" width="100%" height="500px" frameborder="1"></iframe></p><hr>
<p>QA Report:<br><iframe src="qa.report" width="100%" height="500px" frameborder="1"></iframe></p>
</body>
</html>
"""

            with open(review_path, "w", encoding="utf-8", errors="replace") as file:
                file.write(review_contents)

            review_created = True

        if not os.path.isfile(review_path):
            raise Exception(f"The HTML review file was not found after creation:\n{review_path}")

        append_tech_tool_audit_log(
            report_folder=version_folder,
            action=f"PrepareReadyPub: InventoryVariable={inventory_variable}; InventoryVersion={inventory_version}",
            target_path=upload_path,
            current_user=current_user
        )

        os.rename(status_file, new_status_file)
        return True

    except Exception:
        if upload_created and os.path.isfile(upload_path):
            try:
                os.remove(upload_path)
            except Exception:
                pass

        for previous_path, previous_contents in replaced_upload_files.items():
            try:
                with open(previous_path, "wb") as file:
                    file.write(previous_contents)
            except Exception:
                pass

        if review_created and os.path.isfile(review_path):
            try:
                os.remove(review_path)
            except Exception:
                pass

        raise

def change_status(app_path, status_file, new_status, report_folder, current_user=None):
    if not status_file or not os.path.isfile(status_file):
        messagebox.showwarning("Missing Status File", "No existing status file was found.")
        return False

    old_status_file = status_file
    new_status_file = os.path.join(app_path, f"{new_status}.status")

    if os.path.abspath(old_status_file).lower() == os.path.abspath(new_status_file).lower(): return False

    if os.path.exists(new_status_file):
        messagebox.showwarning("Status File Exists", f"That status file already exists:\n{new_status_file}")
        return False

    os.rename(old_status_file, new_status_file)

    append_tech_tool_audit_log(
        report_folder=report_folder,
        action=f"ResetStatus to {new_status}",
        target_path=old_status_file,
        current_user=current_user
    )

    return True

def change_status_with_reason(app_path, status_file, new_status, reason, report_folder, current_user=None):
    if not status_file or not os.path.isfile(status_file):
        messagebox.showwarning("Missing Status File", "No existing status file was found.")
        return False

    reason = (reason or "").strip()

    if not reason:
        messagebox.showwarning("Reason Required", "Enter a reason for this status change.")
        return False

    with open(status_file, "r", encoding="utf-8", errors="replace") as file: original_contents = file.read()
    updated_contents = f"{original_contents.rstrip()},{reason}"

    try:
        with open(status_file, "w", encoding="utf-8", errors="replace") as file:
            file.write(updated_contents)

        changed = change_status(app_path=app_path, status_file=status_file, new_status=new_status, report_folder=report_folder, current_user=current_user)

        if not changed:
            with open(status_file, "w", encoding="utf-8", errors="replace") as file: file.write(original_contents)
            return False

        append_tech_tool_audit_log(report_folder=report_folder, comment_text=f"{new_status} reason: {reason}", current_user=current_user)
        return True

    except Exception:
        if os.path.isfile(status_file):
            try:
                with open(status_file, "w", encoding="utf-8", errors="replace") as file: file.write(original_contents)
            except Exception: pass

        raise

def deny_package(app_path, status_file, reason, delete_files, report_folder, current_user=None):
    if not app_path or not os.path.isdir(app_path):
        messagebox.showwarning("Missing Package Folder", "No package folder was found.")
        return False

    if not status_file or not os.path.isfile(status_file):
        messagebox.showwarning("Missing Status File", "No existing status file was found.")
        return False

    reason = (reason or "").strip()

    if not reason:
        messagebox.showwarning("Reason Required", "Enter a reason for denying this package.")
        return False

    denied_status_file = os.path.join(app_path, "DENIED.status")

    if os.path.normcase(os.path.abspath(status_file)) == os.path.normcase(os.path.abspath(denied_status_file)):
        messagebox.showwarning("Already Denied", "This package is already set to DENIED.")
        return False

    if os.path.exists(denied_status_file):
        messagebox.showwarning("Status File Exists", f"That status file already exists:\n{denied_status_file}")
        return False

    with open(status_file, "r", encoding="utf-8", errors="replace") as file: original_contents = file.read()

    version = original_contents.split(",", 1)[0].strip()
    denied_contents = f"{version},{reason}"

    try:
        with open(status_file, "w", encoding="utf-8", errors="replace") as file: file.write(denied_contents)

        os.rename(status_file, denied_status_file)

        append_tech_tool_audit_log(
            report_folder=report_folder,
            action=f"ResetStatus to DENIED; DeleteFiles={delete_files}",
            target_path=status_file,
            current_user=current_user
        )

        append_tech_tool_audit_log(
            report_folder=report_folder,
            comment_text=f"DENIED reason: {reason}",
            current_user=current_user
        )

        if delete_files:
            for entry in os.scandir(app_path):
                if os.path.normcase(os.path.abspath(entry.path)) == os.path.normcase(os.path.abspath(denied_status_file)): continue
                if entry.is_dir(): shutil.rmtree(entry.path)
                else: os.remove(entry.path)

        return True

    except Exception:
        if os.path.isfile(denied_status_file) and not os.path.exists(status_file):
            try:
                os.rename(denied_status_file, status_file)
                with open(status_file, "w", encoding="utf-8", errors="replace") as file: file.write(original_contents)
            except Exception:
                pass

        raise

def update_inventory_variables(app_path, new_inventory_name=None, new_inventory_version=None, report_folder=None, current_user=None):
    if not app_path or not os.path.isdir(app_path):
        messagebox.showwarning("Missing Path", "No package path was found.")
        return False

    new_inventory_name = (new_inventory_name or "").strip()
    new_inventory_version = (new_inventory_version or "").strip()

    if not new_inventory_name and not new_inventory_version:
        messagebox.showwarning("Missing Inventory Variables", "Enter an inventory name, inventory version, or both.")
        return False

    variables_xml_path = os.path.join(app_path, "Variables.xml")

    if not os.path.isfile(variables_xml_path):
        messagebox.showwarning("Missing Variables.xml", f"Variables.xml was not found:\n{variables_xml_path}")
        return False

    tree = ET.parse(variables_xml_path)
    root = tree.getroot()
    updated_items = []

    def update_variable_file_and_xml(file_prefix, new_value, display_name):
        if not new_value:
            return True

        variable_files = [
            entry
            for entry in os.scandir(app_path)
            if entry.is_file()
            and entry.name.lower().endswith(".variable")
            and entry.name.lower().startswith(file_prefix.lower())
        ]

        if not variable_files:
            messagebox.showwarning("Missing Variable File", f"No {file_prefix}*.variable file was found.")
            return False

        if len(variable_files) > 1:
            messagebox.showwarning("Multiple Variable Files", f"More than one {file_prefix}*.variable file was found. Please clean this up before updating.")
            return False

        variable_path = variable_files[0].path
        variable_name = os.path.splitext(variable_files[0].name)[0]

        matching_variable = None

        for custom_variable in root.iter("CustomVariable"):
            name_element = custom_variable.find("Name")

            if name_element is not None and (name_element.text or "").strip() == variable_name:
                matching_variable = custom_variable
                break

        if matching_variable is None:
            messagebox.showwarning("Variable Not Found", f"No CustomVariable Name matched:\n{variable_name}")
            return False

        value_element = matching_variable.find("Value")
        if value_element is None:
            value_element = ET.SubElement(matching_variable, "Value")

        old_xml_value = value_element.text or ""
        value_element.text = new_value

        old_file_value = ""
        if os.path.isfile(variable_path):
            with open(variable_path, "r", encoding="utf-8", errors="replace") as file:
                old_file_value = file.read().strip()

        if old_file_value != new_value:
            with open(variable_path, "w", encoding="utf-8", errors="replace") as file:
                file.write(new_value)

        updated_items.append(f"{display_name} from '{old_xml_value}' to '{new_value}'")
        return True

    if not update_variable_file_and_xml("AppName", new_inventory_name, "InventoryName"):
        return False

    if not update_variable_file_and_xml("AppVer", new_inventory_version, "InventoryVersion"):
        return False

    tree.write(variables_xml_path, encoding="utf-8", xml_declaration=True)

    append_tech_tool_audit_log(
        report_folder=report_folder,
        action="UpdateInventoryVariables: " + "; ".join(updated_items),
        target_path=variables_xml_path,
        current_user=current_user
    )

    return True

def get_inventory_variable_value(app_path, file_prefix):
    if not app_path or not os.path.isdir(app_path):
        return ""

    variable_files = [
        entry
        for entry in os.scandir(app_path)
        if entry.is_file()
        and entry.name.lower().endswith(".variable")
        and entry.name.lower().startswith(file_prefix.lower())
    ]

    if len(variable_files) != 1:
        return ""

    variable_path = variable_files[0].path
    variable_name = os.path.splitext(variable_files[0].name)[0]
    variables_xml_path = os.path.join(app_path, "Variables.xml")

    if file_prefix.lower() == "appver":
        try:
            with open(variable_path, "r", encoding="utf-8", errors="replace") as file:
                return file.read().strip()
        except Exception:
            return ""

    if not os.path.isfile(variables_xml_path):
        return ""

    try:
        tree = ET.parse(variables_xml_path)
        root = tree.getroot()

        for custom_variable in root.iter("CustomVariable"):
            name_element = custom_variable.find("Name")

            if name_element is not None and (name_element.text or "").strip() == variable_name:
                value_element = custom_variable.find("Value")
                return (value_element.text or "").strip() if value_element is not None else ""

    except Exception:
        return ""

    return ""

def get_install_parameters_value(app_path):
    if not app_path or not os.path.isdir(app_path):
        return ""

    parameters_path = os.path.join(app_path, "SILENT.parameters")

    if not os.path.isfile(parameters_path):
        return ""

    try:
        with open(parameters_path, "r", encoding="utf-8", errors="replace") as file:
            return file.read().strip()
    except Exception:
        return ""


def update_install_parameters(app_path, version_folder, new_parameters, report_folder=None, current_user=None):
    if not app_path or not os.path.isdir(app_path):
        messagebox.showwarning("Missing Path", "No package path was found.")
        return False

    parameters_path = os.path.join(app_path, "SILENT.parameters")

    if not os.path.isfile(parameters_path):
        messagebox.showwarning("Missing SILENT.parameters", f"SILENT.parameters was not found:\n{parameters_path}")
        return False

    if not version_folder or not os.path.isdir(version_folder):
        messagebox.showwarning("Missing Version Folder", "No version folder was found.")
        return False

    xml_files = [
        entry
        for entry in os.scandir(version_folder)
        if entry.is_file() and entry.name.lower().endswith(".xml")
    ]

    if not xml_files:
        messagebox.showwarning("Missing XML", f"No XML file was found in:\n{version_folder}")
        return False

    xml_files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    xml_path = xml_files[0].path

    new_parameters = new_parameters or ""

    with open(parameters_path, "w", encoding="utf-8", errors="replace") as file:
        file.write(new_parameters)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    parameter_elements = list(root.iter("Parameters"))

    if not parameter_elements:
        messagebox.showwarning("Parameters Not Found", f"No <Parameters> element was found in:\n{xml_path}")
        return False

    for parameter_element in parameter_elements:
        parameter_element.text = new_parameters

    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    append_tech_tool_audit_log(
        report_folder=report_folder,
        action=f"UpdateInstallParameters: {new_parameters}",
        target_path=xml_path,
        current_user=current_user
    )

    return True

# ==========================================
# URL Actions
# ==========================================

def get_first_https_url(text):
    if not text: return ""

    match = re.search(r"https://[^\r\n;]+", text)
    if not match: return ""

    return match.group(0).strip()


def is_virustotal_gui_url(url):
    if not url: return False
    return url.lower().startswith(VIRUSTOTAL_GUI_PREFIX.lower())


def should_show_launch_url(reason):
    url = get_first_https_url(reason)
    if not url: return False, ""
    if is_virustotal_gui_url(url): return False, url
    return True, url


def should_show_launch_virustotal(reason):
    url = get_first_https_url(reason)
    if not url: return False, ""

    if is_virustotal_gui_url(url): return True, url

    return True, f"https://www.virustotal.com/gui/search?query={url}"

def launch_url(url):
    if not url:
        messagebox.showwarning("Missing URL", "No URL was found.")
        return False

    webbrowser.open(url)
    return True