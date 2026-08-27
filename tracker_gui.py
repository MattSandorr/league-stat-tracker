"""Tkinter dashboard for the personal tracker and dynamic build assistant.

This module is intentionally a presentation layer. It calls the existing tracker,
collector, and recommendation functions without changing their behavior.
"""

from __future__ import annotations

import contextlib
import io
import json
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Callable, Mapping, Sequence

import build_collector
import build_database
import database
import live_build_assistant
import stats


ROLE_CHOICES = ("Automatic", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT")


def format_personal_stats(matches: Sequence[Mapping[str, Any]]) -> str:
    if not matches:
        return (
            "No personal matches are stored yet.\n\n"
            "Your build database and personal tracker database are separate. "
            "Collecting build samples does not automatically add games here."
        )

    kda = stats.average_kda(matches)
    most_played = stats.most_played_champ(matches)
    role_rates = stats.win_by_role(matches)
    champion_pool = stats.champ_pool(matches)

    lines = [
        f"Games tracked: {len(matches)}",
        f"Overall win rate: {stats.win_rate(matches):.1f}%",
        f"Last 10 win rate: {stats.win_rate_past_games(matches, 10):.1f}%",
    ]
    if kda:
        lines.append(
            "Average K / D / A: "
            f"{kda['avg_kills']:.1f} / {kda['avg_deaths']:.1f} / "
            f"{kda['avg_assists']:.1f}"
        )
    if most_played:
        game_label = "game" if most_played[1] == 1 else "games"
        lines.append(
            f"Most played: {most_played[0]} ({most_played[1]} {game_label})"
        )

    lines.extend(("", "Win rate by role:"))
    if role_rates:
        lines.extend(
            f"  {role or 'UNKNOWN'}: {win_rate:.1f}%"
            for role, win_rate in sorted(role_rates.items())
        )
    else:
        lines.append("  No role data")

    lines.extend(("", "Champion pool:"))
    lines.extend(
        f"  {champion}: {games} {'game' if games == 1 else 'games'}"
        for champion, games in champion_pool
    )
    return "\n".join(lines)


def format_collection_counts(counts: Mapping[str, int]) -> str:
    labels = {
        "build_matches": "Matches",
        "build_participants": "Participant builds",
        "final_items": "Final item slots",
        "item_events": "Item timeline events",
        "team_bans": "Team bans",
    }
    return "\n".join(
        f"{labels.get(key, key)}: {value:,}" for key, value in counts.items()
    )


def format_live_recommendation(result: Mapping[str, Any]) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        live_build_assistant.print_recommendation(result)
    return output.getvalue().strip()


def replace_text(widget: scrolledtext.ScrolledText, value: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", tk.END)
    widget.insert("1.0", value)
    widget.configure(state="disabled")


class TrackerApp:
    """Coordinate the Tkinter views with the existing tracker services."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("League Tracker & Build Assistant")
        self.root.geometry("940x700")
        self.root.minsize(760, 560)

        self.name_var = tk.StringVar(value="Matchu")
        self.tag_var = tk.StringVar(value="420")
        self.live_role_var = tk.StringVar(value="Automatic")
        self.lane_opponent_var = tk.StringVar()
        self.puuid_var = tk.StringVar()
        self.match_count_var = tk.IntVar(value=20)
        self.include_old_patches_var = tk.BooleanVar(value=False)

        self._configure_style()
        self._build_account_header()
        self._build_tabs()
        self.refresh_personal_stats()
        self.refresh_build_coverage()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", foreground="#555555")
        style.configure("TNotebook.Tab", padding=(14, 8))

    def _build_account_header(self) -> None:
        header = ttk.Frame(self.root, padding=(16, 14, 16, 8))
        header.pack(fill="x")
        header.columnconfigure(5, weight=1)

        ttk.Label(header, text="League Tracker", style="Title.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 10)
        )
        ttk.Label(header, text="Riot name").grid(row=1, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.name_var, width=22).grid(
            row=1, column=1, sticky="w", padx=(8, 18)
        )
        ttk.Label(header, text="Tag").grid(row=1, column=2, sticky="w")
        ttk.Entry(header, textvariable=self.tag_var, width=10).grid(
            row=1, column=3, sticky="w", padx=(8, 18)
        )
        ttk.Label(
            header,
            text="Used for live detection and optional PUUID lookup",
            style="Status.TLabel",
        ).grid(row=1, column=4, columnspan=2, sticky="w")

    def _build_tabs(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.personal_tab = ttk.Frame(notebook, padding=14)
        self.live_tab = ttk.Frame(notebook, padding=14)
        self.data_tab = ttk.Frame(notebook, padding=14)
        notebook.add(self.personal_tab, text="Personal Stats")
        notebook.add(self.live_tab, text="Live Build")
        notebook.add(self.data_tab, text="Build Data")

        self._build_personal_tab()
        self._build_live_tab()
        self._build_data_tab()

    def _build_personal_tab(self) -> None:
        self.personal_tab.rowconfigure(2, weight=1)
        self.personal_tab.columnconfigure(0, weight=1)

        ttk.Label(
            self.personal_tab,
            text="Your saved match history",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            self.personal_tab,
            text="Refresh Stats",
            command=self.refresh_personal_stats,
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(
            self.personal_tab,
            text="Reads data/tracker.db. This tab does not call Riot automatically.",
            style="Status.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

        self.personal_output = scrolledtext.ScrolledText(
            self.personal_tab,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.personal_output.grid(row=2, column=0, columnspan=2, sticky="nsew")

    def _build_live_tab(self) -> None:
        self.live_tab.rowconfigure(3, weight=1)
        self.live_tab.columnconfigure(3, weight=1)

        ttk.Label(self.live_tab, text="Role override").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Combobox(
            self.live_tab,
            textvariable=self.live_role_var,
            values=ROLE_CHOICES,
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky="w", padx=(8, 20))

        ttk.Label(self.live_tab, text="Lane opponent override").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Entry(
            self.live_tab,
            textvariable=self.lane_opponent_var,
            width=22,
        ).grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Button(
            self.live_tab,
            text="Detect Live Game & Recommend",
            command=self.request_live_recommendation,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 8))

        self.live_status_var = tk.StringVar(
            value="Start a game, then click Detect Live Game & Recommend."
        )
        ttk.Label(
            self.live_tab,
            textvariable=self.live_status_var,
            style="Status.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.live_output = scrolledtext.ScrolledText(
            self.live_tab,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.live_output.grid(row=3, column=0, columnspan=4, sticky="nsew")

    def _build_data_tab(self) -> None:
        self.data_tab.rowconfigure(5, weight=1)
        self.data_tab.columnconfigure(1, weight=1)

        ttk.Label(self.data_tab, text="PUUID (optional)").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(self.data_tab, textvariable=self.puuid_var).grid(
            row=0, column=1, columnspan=4, sticky="ew", padx=(8, 0)
        )
        ttk.Label(
            self.data_tab,
            text="Leave blank to look it up from the Riot name and tag above.",
            style="Status.TLabel",
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 10))

        ttk.Label(self.data_tab, text="Matches").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(
            self.data_tab,
            from_=1,
            to=100,
            textvariable=self.match_count_var,
            width=7,
        ).grid(row=2, column=1, sticky="w", padx=(8, 18))
        ttk.Checkbutton(
            self.data_tab,
            text="Include older patches",
            variable=self.include_old_patches_var,
        ).grid(row=2, column=2, sticky="w")
        ttk.Button(
            self.data_tab,
            text="Collect Matches",
            command=self.request_match_collection,
        ).grid(row=2, column=3, sticky="w", padx=(18, 8))
        ttk.Button(
            self.data_tab,
            text="Refresh Coverage",
            command=self.refresh_build_coverage,
        ).grid(row=2, column=4, sticky="e")

        self.data_status_var = tk.StringVar(value="Ready")
        ttk.Label(
            self.data_tab,
            textvariable=self.data_status_var,
            style="Status.TLabel",
        ).grid(row=3, column=0, columnspan=5, sticky="w", pady=(10, 8))

        self.coverage_var = tk.StringVar()
        ttk.Label(
            self.data_tab,
            textvariable=self.coverage_var,
            justify="left",
            font=("Consolas", 10),
        ).grid(row=4, column=0, columnspan=5, sticky="w", pady=(0, 10))

        self.data_output = scrolledtext.ScrolledText(
            self.data_tab,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.data_output.grid(row=5, column=0, columnspan=5, sticky="nsew")

    def refresh_personal_stats(self) -> None:
        try:
            database.init_db()
            matches = database.get_all_matches()
            replace_text(self.personal_output, format_personal_stats(matches))
        except Exception as exc:  # The GUI boundary must display backend failures.
            replace_text(self.personal_output, f"Could not load personal stats:\n{exc}")

    def refresh_build_coverage(self) -> None:
        try:
            counts = build_database.get_collection_counts()
            self.coverage_var.set(format_collection_counts(counts))
        except Exception as exc:  # The GUI boundary must display backend failures.
            self.coverage_var.set(f"Could not load build database: {exc}")

    def _validated_riot_id(self) -> tuple[str, str]:
        name = self.name_var.get().strip()
        tag = self.tag_var.get().strip().lstrip("#")
        if not name or not tag:
            raise ValueError("Enter both a Riot name and tag at the top of the window.")
        return name, tag

    def request_live_recommendation(self) -> None:
        try:
            name, tag = self._validated_riot_id()
        except ValueError as exc:
            messagebox.showerror("Missing Riot ID", str(exc), parent=self.root)
            return

        selected_role = self.live_role_var.get()
        role = None if selected_role == "Automatic" else selected_role
        lane_opponent = self.lane_opponent_var.get().strip() or None
        self.live_status_var.set("Detecting the live game and building a recommendation...")

        def task() -> dict[str, Any]:
            return live_build_assistant.create_live_recommendation(
                name,
                tag,
                role=role,
                lane_opponent=lane_opponent,
            )

        def succeeded(result: dict[str, Any]) -> None:
            replace_text(self.live_output, format_live_recommendation(result))
            self.live_status_var.set("Recommendation ready")

        def failed(exc: Exception) -> None:
            replace_text(self.live_output, f"Live build assistant error:\n{exc}")
            self.live_status_var.set("Could not create a recommendation")

        self._run_background(task, succeeded, failed)

    def request_match_collection(self) -> None:
        try:
            count = int(self.match_count_var.get())
            if not 1 <= count <= 100:
                raise ValueError
        except (TypeError, ValueError, tk.TclError):
            messagebox.showerror(
                "Invalid match count",
                "Choose a match count from 1 through 100.",
                parent=self.root,
            )
            return

        supplied_puuid = self.puuid_var.get().strip()
        if not supplied_puuid:
            try:
                name, tag = self._validated_riot_id()
            except ValueError as exc:
                messagebox.showerror("Missing player", str(exc), parent=self.root)
                return
        else:
            name = tag = ""

        include_old = self.include_old_patches_var.get()
        self.data_status_var.set("Collecting matches from Riot...")

        def task() -> dict[str, Any]:
            puuid = supplied_puuid or live_build_assistant.get_account_puuid(name, tag)
            return build_collector.collect_matches_for_puuid(
                puuid,
                count=count,
                current_patch_only=not include_old,
            )

        def succeeded(summary: dict[str, Any]) -> None:
            replace_text(self.data_output, json.dumps(summary, indent=2))
            self.data_status_var.set("Collection finished")
            self.refresh_build_coverage()

        def failed(exc: Exception) -> None:
            replace_text(self.data_output, f"Match collector error:\n{exc}")
            self.data_status_var.set("Collection failed")

        self._run_background(task, succeeded, failed)

    def _run_background(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_failure: Callable[[Exception], None],
    ) -> None:
        """Execute blocking Riot work while keeping the Tkinter window responsive."""

        def worker() -> None:
            try:
                result = task()
            except Exception as exc:  # The UI boundary reports all backend failures.
                self.root.after(0, lambda error=exc: on_failure(error))
            else:
                self.root.after(0, lambda value=result: on_success(value))

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    TrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
