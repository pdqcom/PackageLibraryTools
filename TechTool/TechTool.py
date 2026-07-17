import ctypes
import os
import re
import threading
import tkinter as tk
import shutil
import actions
import getpass
from tkinter import ttk, filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_REPO = r"\\pl-scraper2\C$\Repo"

STATUS_STYLES = {
    "failed": {
        "statuses": ("FAILED",),
        "background": "#B00020",
        "foreground": "white",
        "label": "Failed",
    },
    "denied": {
        "statuses": ("DENIED",),
        "background": "#666666",
        "foreground": "white",
        "label": "Denied",
    },
    "hold": {
        "statuses": ("HOLD",),
        "background": "#6A0DAD",
        "foreground": "white",
        "label": "On Hold",
    },
    "ready_pub": {
        "statuses": ("READY_PUB",),
        "background": "#2E7D32",
        "foreground": "white",
        "label": "Ready for Pub",
    },
    "ready_qa": {
        "statuses": ("READY_QA",),
        "background": "#1E88E5",
        "foreground": "white",
        "label": "Ready for QA",
    },
    "success_pub": {
        "statuses": ("SUCCESS_PUB",),
        "background": "white",
        "foreground": "black",
        "label": "Published",
    },
    "in_transit": {
        "statuses": (),
        "background": "#FFF59D",
        "foreground": "black",
        "label": "In Transit",
    },
}

STATUS_CHANGE_OPTIONS = [
    "READY_Security",
    "FAILED_Security",
    "READY_QA",
    "FAILED_QA",
    "READY_Pub",
    "FAILED_Pub",
    "SUCCESS_Pub",
    "DENIED",
    "HOLD",
]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def center_window_on_mouse_monitor(window, width, height):
    try:
        user32 = ctypes.windll.user32

        cursor_position = POINT()
        user32.GetCursorPos(ctypes.byref(cursor_position))

        monitor = user32.MonitorFromPoint(cursor_position, 2)

        monitor_info = MONITORINFO()
        monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info))

        work_area = monitor_info.rcWork
        monitor_width = work_area.right - work_area.left
        monitor_height = work_area.bottom - work_area.top

        x = work_area.left + ((monitor_width - width) // 2)
        y = work_area.top + ((monitor_height - height) // 2)

        window.geometry(f"{width}x{height}+{x}+{y}")

    except Exception:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()

        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        window.geometry(f"{width}x{height}+{x}+{y}")


class CheckBoxDropdown(ttk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent)

        self.on_change = on_change
        self.status_vars = {}
        self.popup = None

        self.button_text = tk.StringVar(value="All statuses")
        self.button = ttk.Button(self, textvariable=self.button_text, command=self.toggle_popup)
        self.button.pack(fill="x")

    def set_options(self, statuses):
        current_values = {
            status: var.get()
            for status, var in self.status_vars.items()
        }

        self.status_vars = {}

        for status in statuses:
            checked = current_values.get(status, True)
            self.status_vars[status] = tk.BooleanVar(value=checked)

        self.update_button_text()

    def get_selected_statuses(self):
        return {
            status
            for status, var in self.status_vars.items()
            if var.get()
        }

    def toggle_popup(self):
        if self.popup and self.popup.winfo_exists():
            self.close_popup(apply_changes=False)
            return

        self.open_popup()

    def open_popup(self):
        self.popup = tk.Toplevel(self)
        self.popup.title("Status Filter")
        self.popup.resizable(False, False)
        self.popup.transient(self.winfo_toplevel())

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.popup.geometry(f"+{x}+{y}")

        container = ttk.Frame(self.popup, padding=8)
        container.pack(fill="both", expand=True)

        button_frame = ttk.Frame(container)
        button_frame.pack(fill="x", pady=(0, 8))

        ttk.Button(button_frame, text="All", command=self.select_all).pack(side="left")
        ttk.Button(button_frame, text="None", command=self.select_none).pack(side="left", padx=5)

        check_frame = ttk.Frame(container)
        check_frame.pack(fill="both", expand=True)

        for status in sorted(self.status_vars):
            check = ttk.Checkbutton(
                check_frame,
                text=status,
                variable=self.status_vars[status],
                command=self.selection_changed
            )
            check.pack(anchor="w", pady=1)

        self.popup.protocol(
            "WM_DELETE_WINDOW",
            lambda: self.close_popup(apply_changes=False)
        )
        self.popup.bind("<FocusOut>", self.close_if_focus_left)

        self.popup.update_idletasks()

        width = self.popup.winfo_reqwidth()
        height = self.popup.winfo_reqheight()

        self.popup.geometry(f"{width}x{height}+{x}+{y}")

        self.popup.lift()
        self.popup.focus_force()

    def close_if_focus_left(self, event=None):
        self.after(100, self.check_popup_focus)

    def check_popup_focus(self):
        if not self.popup or not self.popup.winfo_exists():
            return

        focused_widget = self.popup.focus_get()

        if focused_widget is None:
            self.close_popup(apply_changes=False)
            return

        try:
            if focused_widget.winfo_toplevel() != self.popup:
                self.close_popup(apply_changes=False)
        except Exception:
            self.close_popup(apply_changes=False)

    def selection_changed(self):
        self.update_button_text()

        if self.on_change:
            self.on_change()

    def select_all(self):
        for var in self.status_vars.values():
            var.set(True)

        self.selection_changed()

    def select_none(self):
        for var in self.status_vars.values():
            var.set(False)

        self.selection_changed()

    def close_popup(self, apply_changes=False):
        if self.popup and self.popup.winfo_exists():
            self.popup.destroy()

        self.popup = None

    def update_button_text(self):
        total = len(self.status_vars)
        selected = len(self.get_selected_statuses())

        if total == 0 or selected == total:
            self.button_text.set("All statuses")
        elif selected == 0:
            self.button_text.set("No statuses")
        else:
            self.button_text.set(f"{selected} of {total} statuses")


class RepoStatusViewer(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Repo Status Viewer")
        self.minsize(900, 500)
        center_window_on_mouse_monitor(self, 1100, 600)

        self.current_user = getpass.getuser()
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.viewer_frame = ViewerFrame(self.container, controller=self)
        self.app_details_frame = AppDetailsFrame(self.container, controller=self)

        self.viewer_frame.grid(row=0, column=0, sticky="nsew")
        self.app_details_frame.grid(row=0, column=0, sticky="nsew")

        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        self.show_viewer()
        self.after(100, self.viewer_frame.scan_repo)
        

    def show_viewer(self, refresh_app_path=None):
        self.title("Repo Status Viewer")
        self.viewer_frame.tkraise()
        self.viewer_frame.focus_viewer()

        if refresh_app_path:
            self.viewer_frame.refresh_single_app(refresh_app_path)

    def show_app_details(self, app_data):
        self.title(f"Repo Status Viewer - {app_data.get('App', '')}")
        self.app_details_frame.load_app(app_data, preferred_report="qa.report", preserve_report=False)
        self.app_details_frame.tkraise()
        self.app_details_frame.focus_details()


class ViewerFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)

        self.controller = controller
        self.repo_path = tk.StringVar(value=DEFAULT_REPO)
        self.search_text = tk.StringVar()
        self.exclude_new_var = tk.BooleanVar(value=False)
        self.exclude_new_text_var = tk.StringVar(value="Exclude New (0)")
        self.bulk_status_var = tk.StringVar(value="Bulk Status Change")


        self.all_apps = []
        self.sort_column = "App"
        self.sort_reverse = False
        self.scan_in_progress = False

        self.build_ui()

    def build_ui(self):
        top_frame = ttk.Frame(self, padding=8)
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="Repo:").pack(side="left")

        repo_entry = ttk.Entry(top_frame, textvariable=self.repo_path)
        repo_entry.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Button(top_frame, text="Browse", command=self.browse_repo).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Refresh", command=self.scan_repo).pack(side="left", padx=2)

        filter_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        filter_frame.pack(fill="x")

        ttk.Label(filter_frame, text="Search:").pack(side="left")

        search_entry = ttk.Entry(filter_frame, textvariable=self.search_text, width=30)
        search_entry.pack(side="left", padx=5)
        search_entry.bind("<KeyRelease>", lambda event: self.apply_filters())

        ttk.Label(filter_frame, text="Status:").pack(side="left", padx=(15, 0))

        self.status_dropdown = CheckBoxDropdown(
            filter_frame,
            on_change=self.apply_filters
        )
        self.status_dropdown.pack(side="left", padx=5)
        self.status_dropdown.button.configure(state="disabled")

        self.exclude_new_checkbox = ttk.Checkbutton(
            filter_frame,
            textvariable=self.exclude_new_text_var,
            variable=self.exclude_new_var,
            command=self.apply_filters
        )
        self.exclude_new_checkbox.pack(side="left", padx=(10, 0))
        self.bulk_status_frame = ttk.Frame(filter_frame)

        ttk.Label(self.bulk_status_frame, text="Bulk Status Change:").pack(side="left", padx=(0, 5))

        self.bulk_status_dropdown = ttk.Combobox(self.bulk_status_frame, textvariable=self.bulk_status_var, values=STATUS_CHANGE_OPTIONS, state="readonly", width=18)
        self.bulk_status_dropdown.pack(side="left", padx=(0, 5))

        ttk.Button(self.bulk_status_frame, text="Update", command=self.bulk_change_status).pack(side="left")

        self.bulk_status_frame.pack(side="right", padx=(10, 0))
        self.bulk_status_frame.pack_forget()

        columns = ("App", "Version", "New", "Status", "Reason")

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")

        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")

        self.tree.heading("App", text="App", command=lambda: self.sort_by("App"))
        self.tree.heading("Version", text="Version", command=lambda: self.sort_by("Version"))
        self.tree.heading("New", text="New", command=lambda: self.sort_by("New"))
        self.tree.heading("Status", text="Status", command=lambda: self.sort_by("Status"))
        self.tree.heading("Reason", text="Reason", command=lambda: self.sort_by("Reason"))

        self.tree.column("App", width=300, anchor="w")
        self.tree.column("Version", width=140, anchor="w")
        self.tree.column("New", width=55, anchor="center")
        self.tree.column("Status", width=180, anchor="w")
        self.tree.column("Reason", width=420, anchor="w")

        self.configure_row_colors()

        self.tree.bind("<Double-1>", self.open_selected_app)
        self.tree.bind("<<TreeviewSelect>>", self.update_bulk_status_visibility)

        bottom_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom_frame.pack(fill="x")

        self.count_label = ttk.Label(bottom_frame, text="")
        self.count_label.pack(side="left")

        legend_frame = ttk.Frame(bottom_frame)
        legend_frame.pack(side="right")

        for style in STATUS_STYLES.values():
            tk.Label(
                legend_frame,
                text=style["label"],
                bg=style["background"],
                fg=style["foreground"],
                relief="solid",
                bd=1,
                padx=6,
                pady=2,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(4, 0))

    def focus_viewer(self):
        self.after_idle(self.tree.focus_set)

    def configure_row_colors(self):
        for tag, style in STATUS_STYLES.items():
            self.tree.tag_configure(
                tag,
                background=style["background"],
                foreground=style["foreground"],
            )

    def get_status_tag(self, status):
        status_upper = status.strip().upper()

        if status_upper.startswith("FAILED"):
            return "failed"
        if status_upper == "DENIED":
            return "denied"
        if status_upper == "HOLD":
            return "hold"
        if status_upper == "READY_PUB":
            return "ready_pub"
        if status_upper == "READY_QA":
            return "ready_qa"
        if status_upper == "SUCCESS_PUB":
            return "success_pub"

        return "in_transit"

    def browse_repo(self):
        selected = filedialog.askdirectory(initialdir=self.repo_path.get())

        if selected:
            self.repo_path.set(selected)
            self.scan_repo()

    def scan_repo(self):
        if self.scan_in_progress:
            return

        repo = self.repo_path.get()

        if not os.path.isdir(repo):
            messagebox.showerror("Invalid Repo", f"Folder does not exist:\n{repo}")
            return

        self.scan_in_progress = True
        self.tree.delete(*self.tree.get_children())
        

        self.tree.insert("", "end", values=("⏳ Loading repository...", "", "", ""))
        self.status_dropdown.button.configure(state="disabled")
        self.count_label.config(text="Scanning repo...")
        self.update_idletasks()

        def worker():
            apps = []

            try:
                app_entries = [
                    entry
                    for entry in os.scandir(repo)
                    if entry.is_dir() and entry.name.lower() not in ("logs", "upload")
                ]

                with ThreadPoolExecutor(max_workers=24) as executor:
                    futures = [
                        executor.submit(self.get_app_data, entry.path, entry.name)
                        for entry in app_entries
                    ]

                    for future in as_completed(futures):
                        apps.append(future.result())

            except Exception as error:
                error_message = str(error)
                self.after(0, lambda message=error_message: self.finish_scan_error(message))
                return

            self.after(0, lambda: self.finish_scan_success(apps))

        threading.Thread(target=worker, daemon=True).start()

    def find_status_file(self, app_path):
        try:
            for entry in os.scandir(app_path):
                if entry.is_file() and entry.name.lower().endswith(".status"):
                    return entry.path
        except Exception: return None

        return None
    
    def has_new_package_file(self, app_path):
        if not app_path: return False
        return os.path.isfile(os.path.join(app_path, "new.package"))

    def get_status_from_filename(self, status_file):
        filename = os.path.basename(status_file)
        status_name, _ = os.path.splitext(filename)
        return status_name

    def read_version_and_reason(self, status_file):
        try:
            with open(status_file, "r", encoding="utf-8", errors="replace") as file:
                contents = file.read().strip()

            if "," in contents:
                version, reason = contents.split(",", 1)
                return version.strip(), reason.strip()

            return contents, ""

        except Exception:
            return "Unreadable Version", ""

    def get_audit_report_path(self, app_path, version):
        if not app_path or not version:
            return ""

        return os.path.join(app_path, version, "audit.report")

    def get_failed_details_from_audit_report(self, audit_report_path):
        if not audit_report_path or not os.path.isfile(audit_report_path):
            return "", ""

        try:
            with open(audit_report_path, "rb") as file:
                file.seek(0, os.SEEK_END)
                file_size = file.tell()

                chunk_size = 8192
                buffer = b""
                position = file_size

                while position > 0:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    file.seek(position)

                    buffer = file.read(read_size) + buffer
                    lines = buffer.splitlines()

                    for raw_line in reversed(lines):
                        try:
                            clean_line = raw_line.decode("utf-8", errors="replace").strip()
                        except Exception:
                            continue

                        if ";FAILED;" in clean_line.upper():
                            parts = clean_line.split(";")

                            failed_step = parts[0].strip() if len(parts) >= 1 else ""
                            failed_reason = parts[2].strip() if len(parts) >= 3 else ""

                            return failed_step, failed_reason

            return "", ""

        except Exception:
            return "", ""

    def get_app_data(self, app_path, app_name=None):
        app_name = app_name or os.path.basename(app_path)
        status_file = self.find_status_file(app_path)
        audit_report_path = ""
        failed_step = ""
        audit_reason = ""

        if status_file:
            status = self.get_status_from_filename(status_file)
            version, status_file_reason = self.read_version_and_reason(status_file)

            reason = ""
            status_upper = status.strip().upper()

            if status_upper in ("HOLD", "DENIED"):
                reason = status_file_reason

            elif status_upper.startswith("FAILED_"):
                audit_report_path = self.get_audit_report_path(app_path, version)
                failed_step, audit_reason = self.get_failed_details_from_audit_report(audit_report_path)

            if audit_reason:
                reason = audit_reason

        else:
            status = "No Status File"
            version = ""
            reason = ""

        is_new = self.has_new_package_file(app_path)

        return {
            "App": app_name,
            "Version": version,
            "New": "✓" if is_new else "",
            "IsNew": is_new,
            "Status": status,
            "FailedStep": failed_step,
            "Reason": reason,
            "StatusFile": status_file or "",
            "AuditReportPath": audit_report_path,
            "Path": app_path
        }

    def refresh_single_app(self, app_path):
        if not app_path or not os.path.isdir(app_path):
            return

        refreshed_app = self.get_app_data(app_path)

        replaced = False
        for index, app in enumerate(self.all_apps):
            if app.get("Path") == app_path:
                self.all_apps[index] = refreshed_app
                replaced = True
                break

        if not replaced:
            self.all_apps.append(refreshed_app)

        self.update_status_filter_options()
        self.exclude_new_text_var.set(f"Exclude New ({sum(app.get('IsNew', False) for app in self.all_apps)})")
        self.apply_filters(keep_focus=True)
        self.select_app_by_path(app_path)

    def update_status_filter_options(self):
        statuses = sorted(set(app["Status"] for app in self.all_apps))
        self.status_dropdown.set_options(statuses)

    def apply_filters(self, keep_focus=False):
        focused_widget = self.focus_get() if keep_focus else None

        search = self.search_text.get().strip().lower()
        selected_statuses = self.status_dropdown.get_selected_statuses()

        filtered = []

        for app in self.all_apps:
            if search and search not in app["App"].lower():
                continue

            if app["Status"] not in selected_statuses:
                continue

            if self.exclude_new_var.get() and app.get("IsNew"):
                continue

            filtered.append(app)

        filtered.sort(
            key=lambda item: str(item[self.sort_column]).lower(),
            reverse=self.sort_reverse
        )

        self.tree.delete(*self.tree.get_children())

        for app in filtered:
            row_tag = self.get_status_tag(app["Status"])

            self.tree.insert(
                "",
                "end",
                values=(
                    app["App"],
                    app["Version"],
                    app["New"],
                    app["Status"],
                    app["Reason"]
                ),
                tags=(
                    row_tag,
                    app["Path"],
                    app["StatusFile"],
                    app["AuditReportPath"],
                    app.get("FailedStep", "")
                )
            )

        self.count_label.config(
            text=f"{len(filtered)} apps shown / {len(self.all_apps)} total"
        )

        if keep_focus and focused_widget and focused_widget.winfo_exists():
            self.after_idle(focused_widget.focus_set)

    def select_app_by_path(self, app_path):
        for item_id in self.tree.get_children():
            tags = self.tree.item(item_id, "tags")

            if len(tags) > 1 and tags[1] == app_path:
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.tree.see(item_id)
                break

    def sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        self.apply_filters(keep_focus=True)

    def open_selected_app(self, event=None):
        selected = self.tree.selection()

        if not selected:
            return

        item_id = selected[0]
        values = self.tree.item(item_id, "values")
        tags = self.tree.item(item_id, "tags")

        app_data = {
            "App": values[0],
            "Version": values[1],
            "New": values[2],
            "IsNew": values[2] == "✓",
            "Status": values[3],
            "Reason": values[4],
            "Path": tags[1] if len(tags) > 1 else "",
            "StatusFile": tags[2] if len(tags) > 2 else "",
            "AuditReportPath": tags[3] if len(tags) > 3 else "",
            "FailedStep": tags[4] if len(tags) > 4 else ""
        }

        self.controller.show_app_details(app_data)

    def finish_scan_success(self, apps):
        self.all_apps = apps
        self.exclude_new_text_var.set(f"Exclude New ({sum(app.get('IsNew', False) for app in self.all_apps)})")
        self.update_status_filter_options()
        self.status_dropdown.button.configure(state="normal")
        self.apply_filters(keep_focus=True)

        self.scan_in_progress = False

        self.update_idletasks()
        self.after(250, self.focus_viewer)

    def finish_scan_error(self, error):
        self.scan_in_progress = False
        self.status_dropdown.button.configure(state="normal")
        self.count_label.config(text="Scan failed")
        messagebox.showerror("Scan Failed", str(error))

    def update_bulk_status_visibility(self, event=None):
        selected_count = len(self.tree.selection())

        if selected_count > 1:
            if not self.bulk_status_frame.winfo_ismapped():
                self.bulk_status_frame.pack(side="right")
        else:
            self.bulk_status_frame.pack_forget()
            self.bulk_status_var.set("Bulk Status Change")


    def get_app_data_from_item(self, item_id):
        values = self.tree.item(item_id, "values")
        tags = self.tree.item(item_id, "tags")

        return {
            "App": values[0],
            "Version": values[1],
            "New": values[2],
            "IsNew": values[2] == "✓",
            "Status": values[3],
            "Reason": values[4],
            "Path": tags[1] if len(tags) > 1 else "",
            "StatusFile": tags[2] if len(tags) > 2 else "",
            "AuditReportPath": tags[3] if len(tags) > 3 else "",
            "FailedStep": tags[4] if len(tags) > 4 else "",
        }


    def get_report_folder_for_app(self, app_data):
        audit_report_path = app_data.get("AuditReportPath", "")
        app_path = app_data.get("Path", "")
        version = app_data.get("Version", "")

        if audit_report_path:
            return os.path.dirname(audit_report_path)

        if app_path and version:
            possible_folder = os.path.join(app_path, version)
            if os.path.isdir(possible_folder):
                return possible_folder

        return ""


    def bulk_change_status(self, event=None):
        new_status = self.bulk_status_var.get()

        if new_status not in STATUS_CHANGE_OPTIONS:
            return

        selected_items = list(self.tree.selection())

        if len(selected_items) < 2:
            return

        selected_apps = [
            self.get_app_data_from_item(item_id)
            for item_id in selected_items
        ]

        changed_paths = []

        try:
            for app_data in selected_apps:
                changed = actions.change_status(
                    app_path=app_data.get("Path", ""),
                    status_file=app_data.get("StatusFile", ""),
                    new_status=new_status,
                    report_folder=self.get_report_folder_for_app(app_data),
                    current_user=getattr(self.controller, "current_user", getpass.getuser())
                )

                if changed:
                    changed_paths.append(app_data.get("Path", ""))

            for app_path in changed_paths:
                self.refresh_single_app(app_path)

            self.bulk_status_var.set("Bulk Status Change")
            self.update_bulk_status_visibility()

        except Exception as error:
            messagebox.showerror("Bulk Status Change Failed", str(error))


class AppDetailsFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)

        self.controller = controller

        self.app_name = ""
        self.app_path = ""
        self.version = ""
        self.status = ""
        self.reason = ""
        self.status_file = ""
        self.audit_report_path = ""
        self.report_paths = {}
        self.is_new = False

        self.app_name_var = tk.StringVar()
        self.version_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.reason_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.version_folder_var = tk.StringVar()
        self.report_var = tk.StringVar()
        self.selected_action_var = tk.StringVar()
        self.audit_comment_var = tk.StringVar()
        self.inventory_name_var = tk.StringVar()
        self.inventory_version_var = tk.StringVar()
        self.inventory_name_status_var = tk.StringVar()
        self.inventory_version_status_var = tk.StringVar()
        self.install_parameters_var = tk.StringVar()
        self.install_parameters_status_var = tk.StringVar()
        self.installer_url_var = tk.StringVar()
        self.installer_location_var = tk.StringVar()
        self.installer_status_var = tk.StringVar()
        self.link_font = font.nametofont("TkDefaultFont").copy()
        self.link_hover_font = self.link_font.copy()
        self.link_hover_font.configure(underline=True)

        self.build_ui()

    def build_ui(self):
        page_frame = ttk.Frame(self, padding=10)
        page_frame.pack(fill="both", expand=True)

        header_frame = ttk.Frame(page_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(
            header_frame,
            text="<",
            command=self.go_back
        ).pack(side="left")

        ttk.Label(header_frame, textvariable=self.app_name_var, font=("Segoe UI", 16, "bold")).pack(side="left", padx=(10, 0))
        ttk.Button(header_frame, text="Refresh", command=self.refresh_page).pack(side="right")

        main_frame = ttk.Frame(page_frame)
        main_frame.pack(fill="both", expand=True)

        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=3)
        main_frame.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        info_frame = ttk.LabelFrame(left_frame, text="App Info", padding=10)
        info_frame.grid(row=0, column=0, sticky="ew")
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="Icon:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="nw", pady=3, padx=(0, 8))

        icon_frame = ttk.Frame(info_frame)
        icon_frame.grid(row=1, column=1, sticky="ew", pady=3)

        self.icon_label = ttk.Label(icon_frame, text="Loading icon...", cursor="hand2")
        self.icon_label.pack(side="left")
        self.icon_label.bind("<Button-1>", self.show_icon_menu)

        ttk.Frame(icon_frame).pack(side="left", fill="x", expand=True)

        self.new_badge_label = tk.Label(icon_frame, text="New", bg="#2E7D32", fg="white", relief="solid", bd=1, padx=10, pady=4, font=("Segoe UI", 11, "bold"))
        self.new_badge_label.pack(side="right")

        self.add_info_row(info_frame, 2, "Version:", self.version_var)
        
        status_row = ttk.Frame(info_frame)
        status_row.grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(status_row, textvariable=self.status_var).pack(side="left")

        self.status_edit_button = ttk.Button(status_row, text="Change Status", command=self.show_status_menu)
        self.status_edit_button.pack(side="left", padx=(0, 0))

        ttk.Label(info_frame, text="Status:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="nw", pady=3, padx=(0, 0))

        self.add_info_row(info_frame, 4, "Reason:", self.reason_var, attr_name="reason")
        self.add_info_row(info_frame, 5, "Path:",   self.path_var, link_command=self.open_app_folder, copy_command=lambda: self.copy_directory(self.app_path))
        self.add_info_row(info_frame, 6, "Version Folder:", self.version_folder_var, link_command=self.open_report_folder, copy_command=lambda: self.copy_directory(self.app_path))

        #### ACTIONS FRAME ######
        self.actions_frame = ttk.LabelFrame(left_frame, text="Actions", padding=10)
        self.actions_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.actions_frame.columnconfigure(0, weight=1)

        self.action_selector = ttk.Combobox(
            self.actions_frame,
            textvariable=self.selected_action_var,
            values=[],
            state="readonly"
        )
        self.action_selector.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.action_selector.bind("<<ComboboxSelected>>", lambda event: self.render_selected_action())

        self.action_content_frame = ttk.Frame(self.actions_frame, padding=8)
        self.action_content_frame.grid(row=1, column=0, sticky="nsew")
        self.action_content_frame.columnconfigure(0, weight=1)

        #Right Frame

        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)

        report_frame = ttk.Frame(right_frame)
        report_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        report_frame.columnconfigure(1, weight=1)

        ttk.Label(report_frame, text="Report:").grid(row=0, column=0, sticky="w", padx=(0, 5))

        self.report_selector = ttk.Combobox(report_frame, textvariable=self.report_var, values=[], state="readonly", width=45)
        self.report_selector.grid(row=0, column=1, sticky="ew")
        self.report_selector.bind("<<ComboboxSelected>>", lambda event: self.load_details())

        text_outer_frame = ttk.Frame(right_frame)
        text_outer_frame.grid(row=1, column=0, sticky="nsew")
        text_outer_frame.rowconfigure(0, weight=1)
        text_outer_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(text_outer_frame, wrap="none", font=("Consolas", 10), state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(text_outer_frame, orient="vertical", command=self.text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(text_outer_frame, orient="horizontal", command=self.text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.text_menu = tk.Menu(self, tearoff=False)
        self.text.bind("<Button-3>", self.show_report_text_menu)

        audit_comment_frame = ttk.Frame(right_frame)
        audit_comment_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        audit_comment_frame.columnconfigure(0, weight=1)

        audit_comment_entry = ttk.Entry(audit_comment_frame, textvariable=self.audit_comment_var)
        audit_comment_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ttk.Button(audit_comment_frame, text="Leave Audit Comment", command=self.leave_audit_comment).grid(row=0, column=1, sticky="e")
            #### Helpers for Actions Pane ####

    def clear_actions_frame(self):
        for widget in self.actions_frame.winfo_children():
            widget.destroy()

        self.actions_frame.columnconfigure(0, weight=1)


    def build_actions_frame(self):
        self.clear_actions_frame()

        ttk.Label(
            self.actions_frame,
            text="Available Actions",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        show_launch_url, reason_url = actions.should_show_launch_url(self.reason)

        if show_launch_url:
            ttk.Label(
                self.actions_frame,
                text="Reason URL:",
                font=("Segoe UI", 9, "bold")
            ).grid(row=1, column=0, sticky="w")

            ttk.Label(
                self.actions_frame,
                text=reason_url,
                wraplength=420
            ).grid(row=2, column=0, sticky="w", pady=(0, 5))

            ttk.Button(
                self.actions_frame,
                text="Launch URL",
                command=lambda url=reason_url: self.launch_reason_url(url)
            ).grid(row=3, column=0, sticky="ew", pady=3)

        else:
            ttk.Label(
                self.actions_frame,
                text="No context actions available.",
                foreground="#666666"
            ).grid(row=1, column=0, sticky="w")


    def launch_reason_url(self, url):
        try:
            launched = actions.launch_url(url)

            if launched:
                actions.append_tech_tool_audit_log(
                    report_folder=self.get_report_folder(),
                    action="LaunchURL",
                    target_path=url,
                    current_user=getattr(self.controller, "current_user", getpass.getuser())
                )

        except Exception as error:
            messagebox.showerror("Launch URL Failed", str(error))

    def add_info_row(self, parent, row, label, variable, attr_name=None, link_command=None, copy_command=None):
        label_widget = ttk.Label(parent, text=label, font=("Segoe UI", 9, "bold"))
        label_widget.grid(row=row, column=0, sticky="nw", pady=3)

        if not link_command:
            value_widget = ttk.Label(parent, textvariable=variable, wraplength=420)
            value_widget.grid(row=row, column=1, sticky="w", pady=3)
        else:
            value_frame = ttk.Frame(parent)
            value_frame.grid(row=row, column=1, sticky="w", pady=3)

            value_label = ttk.Label(value_frame, textvariable=variable)
            value_label.pack(side="left")

            open_link = tk.Label(value_frame, text="[Open]", fg="#0563C1", cursor="hand2", font=self.link_font)
            open_link.pack(side="left", padx=(0, 0))
            open_link.bind("<Button-1>", lambda e: link_command())
            open_link.bind("<Enter>", lambda e: open_link.configure(font=self.link_hover_font))
            open_link.bind("<Leave>", lambda e: open_link.configure(font=self.link_font))

            if copy_command:
                copy_link = tk.Label(value_frame, text="[Copy]", fg="#0563C1", cursor="hand2", font=self.link_font)
                copy_link.pack(side="left", padx=(0, 0))
                copy_link.bind("<Button-1>", lambda e: copy_command())
                copy_link.bind("<Enter>", lambda e: copy_link.configure(font=self.link_hover_font))
                copy_link.bind("<Leave>", lambda e: copy_link.configure(font=self.link_font))

            value_widget = value_frame

        if attr_name:
            setattr(self, f"{attr_name}_label", label_widget)
            setattr(self, f"{attr_name}_widget", value_widget)

    def load_app(self, app_data, preferred_report=None, preserve_report=True, preferred_action=None):
        self.app_name = app_data.get("App", "")
        self.app_path = app_data.get("Path", "")
        self.version = app_data.get("Version", "")
        self.is_new = bool(app_data.get("IsNew"))
        self.status = app_data.get("Status", "")
        self.reason = app_data.get("Reason", "")
        self.status_file = app_data.get("StatusFile", "")
        self.audit_report_path = app_data.get("AuditReportPath", "")
        self.failed_step = app_data.get("FailedStep", "")

        self.report_paths = self.find_report_files()

        self.app_name_var.set(self.app_name)
        self.version_var.set(self.version)
        self.status_var.set(self.status)
        self.reason_var.set(self.reason)
        if self.reason.strip():
            self.reason_label.grid()
            self.reason_widget.grid()
        else:
            self.reason_label.grid_remove()
            self.reason_widget.grid_remove()

        if self.is_new:
            self.new_badge_label.pack(side="left", padx=(12, 0))
        else:
            self.new_badge_label.pack_forget()


        self.path_var.set(self.shorten_path(self.format_repo_path(self.app_path),50))
        self.version_folder_var.set(self.shorten_path(self.format_repo_path(self.get_report_folder()), 50))

        report_names = list(self.report_paths.keys())
        self.report_selector.configure(values=report_names)

        if report_names:
            self.report_selector.configure(state="readonly")

            current_report = self.report_var.get()

            preferred_report_match = next((name for name in report_names if preferred_report and name.lower() == preferred_report.lower()), None)

            if preferred_report_match:
                selected_report = preferred_report_match
            elif preserve_report and current_report in report_names:
                selected_report = current_report
            else:
                selected_report = next((name for name in report_names if name.lower() == "qa.report"), report_names[0])

            self.report_var.set(selected_report)
        else:
            self.report_selector.configure(state="disabled")
            self.report_var.set("")

        self.load_app_icon()
        self.load_details()
        self.load_actions(preferred_action=preferred_action)

        

    def shorten_path(self, path, max_length=45):
        if not path: return ""
        if len(path) <= max_length: return path
        return path[:max_length - 3] + "..."

    def focus_details(self):
        self.after_idle(self.text.focus_set)

    def go_back(self):
        self.controller.show_viewer(refresh_app_path=self.app_path)

    def get_report_folder(self):
        if self.audit_report_path:
            return os.path.dirname(self.audit_report_path)

        if self.app_path and self.version:
            possible_folder = os.path.join(self.app_path, self.version)
            if os.path.isdir(possible_folder):
                return possible_folder

        return ""

    def find_report_files(self):
        report_paths = {}
        report_folder = self.get_report_folder()

        if not report_folder or not os.path.isdir(report_folder):
            return report_paths

        try:
            report_files = [
                entry
                for entry in os.scandir(report_folder)
                if entry.is_file() and entry.name.lower().endswith(".report")
            ]

            report_files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)

            for entry in report_files:
                report_paths[entry.name] = entry.path

        except Exception:
            return {}

        return report_paths
        
    def show_report_text_menu(self, event):
        menu = tk.Menu(self, tearoff=False)

        try:
            self.text.selection_get()
            menu.add_command(label="Copy", command=lambda: self.clipboard_append(self.text.selection_get()))
        except tk.TclError:
            menu.add_command(label="Copy", state="disabled")

        menu.add_command(label="Select All", command=lambda: (self.text.tag_add("sel", "1.0", "end-1c"), self.text.focus_set()))
        menu.tk_popup(event.x_root, event.y_root)

    def format_repo_path(self, path):
        if not path:
            return ""

        repo = self.controller.viewer_frame.repo_path.get()

        if path.lower().startswith(repo.lower()):
            return "$(Repo)" + path[len(repo):]

        return path
    
    def expand_repo_path(self, path):
        if not path:
            return ""

        repo = self.controller.viewer_frame.repo_path.get()

        if path.lower().startswith("$(repo)"):
            return repo + path[len("$(Repo)"):]

        return path

    def open_path(self, path):
        actions.open_path(path)

    def open_app_folder(self):
        self.open_path(self.app_path)

    def open_report_folder(self):
        self.open_path(self.get_report_folder())

    def open_status_file(self):
        self.open_path(self.status_file)

    def load_details(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        selected_report = self.report_var.get()
        report_path = self.report_paths.get(selected_report, "")

        if report_path and os.path.isfile(report_path):
            try:
                with open(report_path, "r", encoding="utf-8", errors="replace") as file:
                    self.text.insert("1.0", file.read())
            except Exception as error:
                self.text.insert("1.0", f"Could not read {selected_report}:\n{error}")

        elif self.status.strip().upper().startswith("FAILED_"):
            self.text.insert("1.0", "A report was expected, but no .report files were found.")
        else:
            self.text.insert("1.0", "No .report files found.")

        self.text.configure(state="disabled")
        self.text.see("end")
        self.after_idle(lambda: self.text.see("end"))
        self.after_idle(self.text.focus_set)

    def get_icon_path(self):
        if not self.app_path:
            return ""

        return os.path.join(self.app_path, "icon.png")


    def load_app_icon(self):
        icon_path = self.get_icon_path()

        self.icon_image = None

        if not icon_path or not os.path.isfile(icon_path):
            self.icon_label.config(text="No icon.png", image="")
            return

        try:
            image = Image.open(icon_path)
            image.thumbnail((96, 96))

            self.icon_image = ImageTk.PhotoImage(image)
            self.icon_label.config(image=self.icon_image, text="")

        except Exception as error:
            self.icon_label.config(text=f"Could not load icon: {error}", image="")


    def show_icon_menu(self, event):
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Replace Icon", command=self.replace_icon)
        menu.tk_popup(event.x_root, event.y_root)


    def replace_icon(self):
        try:
            changed = actions.replace_icon(
                app_path=self.app_path,
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Replace Icon Failed", str(error))

    def copy_directory(self, source_path):
        try:
            actions.copy_directory(
                source_path=source_path,
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

        except Exception as error:
            messagebox.showerror("Copy Failed", str(error))
    
    def refresh_page(self, preferred_report=None):
        selected_action = self.selected_action_var.get()
        refreshed_app_data = self.controller.viewer_frame.get_app_data(app_path=self.app_path, app_name=self.app_name)
        self.load_app(refreshed_app_data, preferred_report=preferred_report, preserve_report=True, preferred_action=selected_action)

    def show_status_menu(self):
        menu = tk.Menu(self, tearoff=False)

        for status in STATUS_CHANGE_OPTIONS:
            menu.add_command(
                label=status,
                command=lambda selected_status=status: self.change_status(selected_status)
            )

        x = self.status_edit_button.winfo_rootx()
        y = self.status_edit_button.winfo_rooty() + self.status_edit_button.winfo_height()
        menu.tk_popup(x, y)

    def change_status(self, new_status):
        try:
            changed = actions.change_status(
                app_path=self.app_path,
                status_file=self.status_file,
                new_status=new_status,
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Status Change Failed", str(error))

    def leave_audit_comment(self):
        comment_text = self.audit_comment_var.get().strip()

        if not comment_text:
            return

        try:
            actions.append_tech_tool_audit_log(
                report_folder=self.get_report_folder(),
                comment_text=comment_text,
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            self.audit_comment_var.set("")
            self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Audit Comment Failed", str(error))


    def load_actions(self, preferred_action=None):
        placeholder_action = "Select an Action..."
        available_actions = [
            placeholder_action,
            "Replace Installer",
            "Update Inventory Variables",
            "Update Install Parameters",
        ]

        show_launch_url, reason_url = actions.should_show_launch_url(self.reason)
        show_launch_vt, vt_url = actions.should_show_launch_virustotal(self.reason)

        self.action_data = {
            "Launch URL": {
                "reason_url": reason_url,
                "show_launch_url": show_launch_url,
                "vt_url": vt_url,
                "show_launch_vt": show_launch_vt,
            }
        }

        if show_launch_url or show_launch_vt:
            available_actions.append("Launch URL")

        self.action_selector.configure(values=available_actions)

        if preferred_action in available_actions:
            selected_action = preferred_action
        elif self.status.strip().upper() == "READY_PUB":
            selected_action = "Update Inventory Variables"
        else:
            selected_action = placeholder_action

        self.selected_action_var.set(selected_action)
        self.render_selected_action()


    def clear_action_content(self):
        for widget in self.action_content_frame.winfo_children():
            widget.destroy()


    def render_selected_action(self):
        self.clear_action_content()

        selected_action = self.selected_action_var.get()
        if selected_action == "Select an Action...": return

        if selected_action == "Replace Installer":
            self.render_replace_installer_action()
            return
        
        if selected_action == "Update Inventory Variables":
            self.render_update_inventory_variables_action()
            return

        if selected_action == "Launch URL":
            self.render_launch_url_action()
            return
        
        if selected_action == "Update Install Parameters":
            self.render_update_install_parameters_action()
            return

    def render_launch_url_action(self):
        data = self.action_data.get("Launch URL", {})
        row = 0

        if data.get("show_launch_url"):
            ttk.Label(self.action_content_frame, text=data["reason_url"], wraplength=420).grid(row=row, column=0, sticky="w", pady=(0, 5))
            row += 1

            ttk.Button(self.action_content_frame, text="Launch URL", command=lambda url=data["reason_url"]: self.launch_action_url("LaunchURL", url)).grid(row=row, column=0, sticky="ew", pady=(0, 10))
            row += 1

        if data.get("show_launch_vt"):
            ttk.Label(self.action_content_frame, text=data["vt_url"], wraplength=420).grid(row=row, column=0, sticky="w", pady=(0, 5))
            row += 1

            ttk.Button(self.action_content_frame, text="Launch VirusTotal", command=lambda url=data["vt_url"]: self.launch_action_url("LaunchVirusTotal", url)).grid(row=row, column=0, sticky="ew")


    def launch_action_url(self, action_name, url):
        try:
            if actions.launch_url(url):
                actions.append_tech_tool_audit_log(report_folder=self.get_report_folder(), action=action_name, target_path=url, current_user=getattr(self.controller, "current_user", getpass.getuser()))
        except Exception as error:
            messagebox.showerror("Launch URL Failed", str(error))

    def render_update_inventory_variables_action(self):
        self.action_content_frame.columnconfigure(0, weight=1)
        current_inventory_name = actions.get_inventory_variable_value(self.app_path, "AppName")
        current_inventory_version = actions.get_inventory_variable_value(self.app_path, "AppVer")

        self.inventory_name_var.set(current_inventory_name)

        version_pattern = r"^\d+(?:\.\d+)*$"

        if current_inventory_version and re.fullmatch(version_pattern, current_inventory_version):
            self.inventory_version_var.set(current_inventory_version)
        else:
            self.inventory_version_var.set(self.version)

        # Inventory Name

        ttk.Label(self.action_content_frame, text="New Inventory Name:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")

        inventory_name_entry = ttk.Entry(
            self.action_content_frame,
            textvariable=self.inventory_name_var
        )
        inventory_name_entry.grid(row=1, column=0, sticky="ew", pady=(3, 8))

        name_button_frame = ttk.Frame(self.action_content_frame)
        name_button_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        name_button_frame.columnconfigure(0, weight=1)
        name_button_frame.columnconfigure(1, weight=1)

        ttk.Label(
            name_button_frame,
            textvariable=self.inventory_name_status_var,
            foreground="green"
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            name_button_frame,
            text="Update",
            command=self.update_inventory_name
        ).grid(row=0, column=1, sticky="e")

        # Inventory Version

        ttk.Label(self.action_content_frame, text="New Inventory Version:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w")

        inventory_version_entry = ttk.Entry(
            self.action_content_frame,
            textvariable=self.inventory_version_var
        )
        inventory_version_entry.grid(row=4, column=0, sticky="ew", pady=(3, 8))

        version_button_frame = ttk.Frame(self.action_content_frame)
        version_button_frame.grid(row=5, column=0, sticky="ew")

        version_button_frame.columnconfigure(0, weight=1)
        version_button_frame.columnconfigure(1, weight=1)

        ttk.Label(
            version_button_frame,
            textvariable=self.inventory_version_status_var,
            foreground="green"
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            version_button_frame,
            text="Update",
            command=self.update_inventory_version
        ).grid(row=0, column=1, sticky="e")

        self.inventory_name_status_var.set("")
        self.inventory_version_status_var.set("")

        inventory_name_entry.bind("<KeyRelease>", lambda e: self.inventory_name_status_var.set(""))
        inventory_version_entry.bind("<KeyRelease>", lambda e: self.inventory_version_status_var.set(""))

        inventory_name_entry.focus_set()


    def update_inventory_name(self):
        try:
            changed = actions.update_inventory_variables(
                app_path=self.app_path,
                new_inventory_name=self.inventory_name_var.get(),
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.inventory_name_status_var.set("Saved!")
                self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Update Inventory Name Failed", str(error))

    def update_inventory_version(self):
        try:
            changed = actions.update_inventory_variables(
                app_path=self.app_path,
                new_inventory_version=self.inventory_version_var.get(),
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.inventory_version_status_var.set("Saved!")
                self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Update Inventory Version Failed", str(error))

    def render_update_install_parameters_action(self):
        self.action_content_frame.columnconfigure(0, weight=1)

        current_parameters = actions.get_install_parameters_value(self.app_path)
        self.install_parameters_var.set(current_parameters)
        self.install_parameters_status_var.set("")

        ttk.Label(
            self.action_content_frame,
            text="New Install Parameters:",
            font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=0, sticky="w")

        parameters_entry = ttk.Entry(
            self.action_content_frame,
            textvariable=self.install_parameters_var
        )
        parameters_entry.grid(row=1, column=0, sticky="ew", pady=(3, 8))

        button_frame = ttk.Frame(self.action_content_frame)
        button_frame.grid(row=2, column=0, sticky="ew")

        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Label(
            button_frame,
            textvariable=self.install_parameters_status_var,
            foreground="green"
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            button_frame,
            text="Update",
            command=self.update_install_parameters
        ).grid(row=0, column=1, sticky="e")

        parameters_entry.bind("<KeyRelease>", lambda e: self.install_parameters_status_var.set(""))
        parameters_entry.focus_set()


    def update_install_parameters(self):
        try:
            changed = actions.update_install_parameters(
                app_path=self.app_path,
                version_folder=self.get_report_folder(),
                new_parameters=self.install_parameters_var.get(),
                report_folder=self.get_report_folder(),
                current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.install_parameters_status_var.set("Saved!")
                self.refresh_page(preferred_report="audit.report")

        except Exception as error:
            messagebox.showerror("Update Install Parameters Failed", str(error))


    def render_replace_installer_action(self):
        self.action_content_frame.columnconfigure(0, weight=1)

        version_folder = self.get_report_folder()
        current_url, default_location = actions.get_installer_download_defaults(version_folder)

        self.installer_url_var.set(current_url)
        self.installer_location_var.set(self.format_repo_path(default_location))
        self.installer_status_var.set("")

        ttk.Label(self.action_content_frame, text="URL:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")

        url_entry = ttk.Entry(self.action_content_frame, textvariable=self.installer_url_var)
        url_entry.grid(row=1, column=0, sticky="ew", pady=(3, 8))

        ttk.Label(self.action_content_frame, text="Location:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w")

        location_entry = ttk.Entry(self.action_content_frame, textvariable=self.installer_location_var)
        location_entry.grid(row=3, column=0, sticky="ew", pady=(3, 8))
        self.after_idle(lambda: location_entry.xview_moveto(1))

        button_frame = ttk.Frame(self.action_content_frame)
        button_frame.grid(row=4, column=0, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Label(button_frame, textvariable=self.installer_status_var, foreground="green").grid(row=0, column=0, sticky="w")
        self.download_replace_button = ttk.Button(button_frame, text="Download and Replace", command=self.download_and_replace_installer)
        self.download_replace_button.grid(row=0, column=1, sticky="e")

        url_entry.bind("<KeyRelease>", lambda event: self.installer_status_var.set(""))
        location_entry.bind("<KeyRelease>", lambda event: self.installer_status_var.set(""))

        url_entry.focus_set()


    def download_and_replace_installer(self):
        self.installer_status_var.set("Downloading...")
        self.download_replace_button.configure(state="disabled")
        self.update_idletasks()

        try:
            changed = actions.download_and_replace_installer(
                version_folder=self.get_report_folder(),
                download_url=self.installer_url_var.get(),
                installer_location=self.expand_repo_path(self.installer_location_var.get()), 
                report_folder=self.get_report_folder(), current_user=getattr(self.controller, "current_user", getpass.getuser())
            )

            if changed:
                self.refresh_page(preferred_report="audit.report")
                self.installer_status_var.set("Success!")
            else:
                self.installer_status_var.set("")

        except Exception as error:
            self.installer_status_var.set("Failed")
            messagebox.showerror("Replace Installer Failed", str(error))

        finally:
            if hasattr(self, "download_replace_button"):
                self.download_replace_button.configure(state="normal")






if __name__ == "__main__":
    app = RepoStatusViewer()
    app.mainloop()
