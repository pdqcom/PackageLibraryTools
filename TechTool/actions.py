import getpass
import os
import re
import shutil
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from tkinter import filedialog, messagebox


# ==========================================
# Constants
# ==========================================

VIRUSTOTAL_GUI_PREFIX = "https://www.virustotal.com/gui/"


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