from __future__ import annotations

import argparse
import asyncio
import json
import os
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static


SCREEN_SLOTS: list[tuple[str, str, bool]] = [
    ("overview", "Overview", True),
    ("threads", "Threads", True),
    ("research", "Research", True),
    ("execution", "Execution", True),
    ("wallet", "Wallet", False),
    ("reports", "Reports", False),
    ("system", "System", False),
]

DEFAULT_BASE_URL = os.environ.get("AUTOTRADER_TUI_BASE_URL", "http://127.0.0.1:8080")
DEFAULT_REFRESH_SECONDS = float(os.environ.get("AUTOTRADER_TUI_REFRESH_SECONDS", "2.5"))
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("AUTOTRADER_TUI_TIMEOUT_SECONDS", "5.0"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso8601(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_timestamp(value: Any) -> str:
    dt = _parse_iso8601(value)
    return dt.astimezone().strftime("%H:%M:%S") if dt else "n/a"


def _format_number(value: Any, precision: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{precision}f}"


def _format_currency(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_signed(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:+.2f}"


def _shorten(value: Any, *, width: int = 80) -> str:
    return "n/a" if value is None else textwrap.shorten(str(value), width=width, placeholder="...")


def _style_for_state(value: str) -> str:
    normalized = value.lower()
    if normalized in {"healthy", "running", "active", "promote", "ok", "true"}:
        return "green"
    if normalized in {"paused", "idle", "stopped", "degraded", "reject", "warn", "waiting"}:
        return "yellow"
    if normalized in {"failed", "error", "critical", "bad"}:
        return "bold red"
    return "grey62"


def _style_for_health(value: str) -> str:
    normalized = value.lower()
    if normalized == "healthy":
        return "green"
    if normalized == "paused":
        return "yellow"
    if normalized == "degraded":
        return "orange1"
    if normalized == "failed":
        return "bold red"
    return "grey62"


def _yesno(value: bool) -> str:
    return "running" if value else "stopped"


@dataclass(slots=True)
class ActionPreview:
    summary: str
    target: str
    expected_result: str
    verify_command: str
    payload: dict[str, Any]


@dataclass(slots=True)
class DashboardSnapshot:
    raw: dict[str, Any]

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self.raw.get("meta") or {})

    @property
    def paper(self) -> dict[str, Any]:
        return dict(self.raw.get("paper") or {})

    @property
    def workbench(self) -> dict[str, Any]:
        return dict(self.raw.get("workbench") or {})

    @property
    def manager(self) -> dict[str, Any]:
        return dict(self.workbench.get("experiment_manager") or {})

    @property
    def summary(self) -> dict[str, Any]:
        return dict(self.manager.get("summary") or {})

    @property
    def experiments(self) -> list[dict[str, Any]]:
        return [dict(item) for item in (self.raw.get("experiments") or []) if isinstance(item, dict)]

    @property
    def events(self) -> list[dict[str, Any]]:
        return [dict(item) for item in (self.raw.get("experiment_events") or []) if isinstance(item, dict)]

    @property
    def actions(self) -> list[dict[str, Any]]:
        return [dict(item) for item in (self.raw.get("actions") or []) if isinstance(item, dict)]

    @property
    def research(self) -> dict[str, Any]:
        return dict(self.raw.get("research") or {})

    @property
    def trading(self) -> dict[str, Any]:
        return dict(self.raw.get("trading") or {})

    @property
    def generated_at(self) -> Any:
        return self.meta.get("generated_at")

    @property
    def leader_id(self) -> str | None:
        value = self.summary.get("leader_id")
        return str(value) if value else None

    @property
    def leader_score(self) -> Any:
        return self.summary.get("leader_score")

    @property
    def active_count(self) -> int:
        return int(self.summary.get("active_count") or 0)

    @property
    def degraded_count(self) -> int:
        return int(self.summary.get("degraded_count") or 0)

    @property
    def failed_count(self) -> int:
        return int(self.summary.get("failed_count") or 0)

    @property
    def paper_equity(self) -> Any:
        paper_engine = self.paper.get("engine") or {}
        return paper_engine.get("equity") or self.trading.get("equity") or self.paper.get("equity")

    @property
    def paper_running(self) -> bool:
        return bool(self.paper.get("running"))

    @property
    def paper_pid(self) -> Any:
        return self.paper.get("pid")

    @property
    def paper_returncode(self) -> Any:
        return self.paper.get("returncode")

    @property
    def manager_state(self) -> str:
        return str(self.manager.get("state") or self.summary.get("manager_state") or "unknown")

    @property
    def manager_pid(self) -> Any:
        return self.manager.get("pid")

    def experiment_at(self, index: int) -> dict[str, Any] | None:
        if not self.experiments:
            return None
        return self.experiments[index % len(self.experiments)]

    def experiment_by_id(self, experiment_id: str | None) -> dict[str, Any] | None:
        if not experiment_id:
            return None
        for item in self.experiments:
            if str(item.get("id")) == experiment_id:
                return item
        return None

    def leader_experiment(self) -> dict[str, Any] | None:
        return self.experiment_by_id(self.leader_id)


class DashboardClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def fetch_dashboard(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/api/dashboard", timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("dashboard payload must be a JSON object")
        return payload

    def control(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(f"{self.base_url}/api/workbench/control", json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("control response must be a JSON object")
        return data


class AutoResearchTUI(App):
    TITLE = "AUTO RESEARCH // COMMAND ROOM"
    CSS = """
    Screen {
        background: #0b0f16;
        color: #d6dde9;
    }

    #topbar, #commandbar {
        background: #101721;
        border: heavy #223045;
        padding: 0 1;
    }

    #topbar {
        dock: top;
        height: 3;
    }

    #commandbar {
        dock: bottom;
        height: 4;
    }

    #main {
        height: 1fr;
    }

    #nav {
        width: 30;
        background: #0e131c;
        border: heavy #223045;
        padding: 0 1;
    }

    #mission {
        width: 1fr;
        background: #0c1118;
        border: heavy #223045;
        padding: 0 1;
    }

    #inspector {
        width: 40;
        background: #0e131c;
        border: heavy #223045;
        padding: 0 1;
    }

    #command_input {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("tab", "cycle_focus", "Cycle focus", show=True),
        Binding("escape", "cancel_pending", "Cancel", show=True),
        Binding("/", "focus_command", "Command", show=True),
        Binding("?", "toggle_help", "Help", show=True),
        Binding("j", "move_down", "Down", show=True),
        Binding("k", "move_up", "Up", show=True),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("s", "stage_primary", "Start/Resume", show=True),
        Binding("p", "stage_pause", "Pause", show=True),
        Binding("x", "stage_stop", "Stop", show=True),
        Binding("v", "show_verify", "Verify", show=True),
        Binding("f", "focus_filter", "Filter", show=True),
        Binding("enter", "confirm_pending", "Confirm", show=False),
    ]

    selected_screen: reactive[str] = reactive("overview")
    selected_thread_index: reactive[int] = reactive(0)
    selected_event_index: reactive[int] = reactive(0)
    selected_position_index: reactive[int] = reactive(0)
    focus_region: reactive[str] = reactive("main")
    loading: reactive[bool] = reactive(True)
    error_message: reactive[str] = reactive("")
    help_visible: reactive[bool] = reactive(False)

    def __init__(self, *, base_url: str, refresh_seconds: float, timeout_seconds: float) -> None:
        super().__init__()
        self.client = DashboardClient(base_url, timeout_seconds)
        self.refresh_seconds = refresh_seconds
        self.snapshot: DashboardSnapshot | None = None
        self.pending_action: ActionPreview | None = None
        self.command_message = "ready"
        self.command_history: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="main"):
            yield Static(id="nav")
            yield Static(id="mission")
            yield Static(id="inspector")
        with Vertical(id="commandbar"):
            yield Static(id="command_status")
            yield Input(placeholder="type a command, or press /", id="command_input")

    async def on_mount(self) -> None:
        self.set_interval(self.refresh_seconds, self.refresh_dashboard)
        await self.refresh_dashboard()

    async def refresh_dashboard(self) -> None:
        self.loading = True
        self.error_message = ""
        self._render_all()
        try:
            payload = await asyncio.to_thread(self.client.fetch_dashboard)
        except Exception as exc:  # noqa: BLE001
            self.snapshot = None
            self.loading = False
            self.error_message = str(exc)
            self._render_all()
            return
        self.snapshot = DashboardSnapshot(payload)
        self.loading = False
        self.error_message = ""
        self._sync_selection()
        self._render_all()

    def _sync_selection(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen not in {slot for slot, _, _ in SCREEN_SLOTS}:
            self.selected_screen = "overview"
        if self.snapshot.experiments:
            self.selected_thread_index %= len(self.snapshot.experiments)
        else:
            self.selected_thread_index = 0
        if self.snapshot.events:
            self.selected_event_index %= len(self.snapshot.events)
        else:
            self.selected_event_index = 0
        positions = self.snapshot.paper.get("positions") or []
        if isinstance(positions, list) and positions:
            self.selected_position_index %= len(positions)
        else:
            self.selected_position_index = 0

    def _render_all(self) -> None:
        self._render_status()
        self._render_nav()
        self._render_mission()
        self._render_inspector()
        self._render_command_status()

    def _render_status(self) -> None:
        topbar = self.query_one("#topbar", Static)
        if self.snapshot is None:
            text = Text()
            text.append("MODE ", style="grey50")
            text.append(self.selected_screen.upper(), style="bold white")
            text.append("  |  API ", style="grey50")
            text.append("offline", style="bold red")
            text.append("  |  refresh ", style="grey50")
            text.append("pending" if self.loading else "idle", style="yellow")
            text.append("  |  hint ", style="grey50")
            text.append("waiting on /api/dashboard", style="grey62")
            if self.error_message:
                text.append("  |  error ", style="grey50")
                text.append(_shorten(self.error_message, width=80), style="bold red")
            topbar.update(Panel(text, border_style="red", title="AUTO RESEARCH // COMMAND ROOM"))
            return

        leader = self.snapshot.leader_id or "n/a"
        leader_score = _format_number(self.snapshot.leader_score, precision=3)
        counts = f"{self.snapshot.active_count}/{self.snapshot.degraded_count}/{self.snapshot.failed_count}"
        auth_user = os.environ.get("USERNAME") or os.environ.get("USER") or "local"
        text = Text()
        text.append("MODE ", style="grey50")
        text.append(self.selected_screen.upper(), style="bold white")
        text.append("  |  AUTH ", style="grey50")
        text.append(auth_user, style="cyan")
        text.append("  |  EQUITY ", style="grey50")
        text.append(_format_currency(self.snapshot.paper_equity), style="green")
        text.append("  |  LEADER ", style="grey50")
        text.append(leader, style="bold white")
        text.append(f" [{leader_score}]", style="grey62")
        text.append("  |  A/D/F ", style="grey50")
        text.append(counts, style="yellow" if self.snapshot.degraded_count or self.snapshot.failed_count else "green")
        text.append("  |  REFRESH ", style="grey50")
        text.append(_format_timestamp(self.snapshot.generated_at), style="grey62")
        border_style = "green" if self.snapshot.degraded_count == 0 and self.snapshot.failed_count == 0 else "yellow"
        topbar.update(Panel(text, border_style=border_style, title="AUTO RESEARCH // COMMAND ROOM"))

    def _render_nav(self) -> None:
        nav = self.query_one("#nav", Static)
        lines: list[Text] = [Text("NAVIGATION", style="bold white"), Text(" ")]
        for slug, label, enabled in SCREEN_SLOTS:
            prefix = "> " if slug == self.selected_screen else "  "
            style = "bold white" if slug == self.selected_screen else ("grey62" if enabled else "grey35")
            suffix = "" if enabled else "  [inactive]"
            lines.append(Text.assemble((prefix, style), (label, style), (suffix, "grey50")))
        lines.extend(
            [
                Text(" "),
                Text("SHORTCUTS", style="bold white"),
                Text("j/k or arrows move", style="grey62"),
                Text("tab cycles focus", style="grey62"),
                Text("/ command bar", style="grey62"),
                Text("r refresh", style="grey62"),
            ]
        )
        nav.update(Panel(Group(*lines), border_style="grey35", title="SURFACES"))

    def _render_mission(self) -> None:
        mission = self.query_one("#mission", Static)
        if self.snapshot is None:
            mission.update(
                Panel(
                    Group(
                        Text("CONNECTION LOST", style="bold red"),
                        Text(" "),
                        Text("The TUI is live, but /api/dashboard is unreachable.", style="grey70"),
                        Text(" "),
                        Text(f"Target: {self.client.base_url}", style="cyan"),
                        Text(f"Error: {_shorten(self.error_message, width=100)}", style="red"),
                        Text(" "),
                        Text("It will retry automatically on the next poll.", style="grey62"),
                    ),
                    border_style="red",
                    title="OVERVIEW",
                )
            )
            return

        if self.help_visible:
            mission.update(self._render_help_panel())
            return

        if self.selected_screen == "overview":
            mission.update(self._render_overview())
        elif self.selected_screen == "threads":
            mission.update(self._render_threads())
        elif self.selected_screen == "execution":
            mission.update(self._render_execution())
        elif self.selected_screen == "research":
            mission.update(self._render_research())
        else:
            mission.update(self._render_future_slot())

    def _render_inspector(self) -> None:
        inspector = self.query_one("#inspector", Static)
        if self.snapshot is None:
            inspector.update(
                Panel(
                    Group(
                        Text("INSPECTOR", style="bold white"),
                        Text(" "),
                        Text("No snapshot loaded.", style="grey62"),
                    ),
                    border_style="grey35",
                    title="DETAIL",
                )
            )
            return

        if self.selected_screen == "threads":
            inspector.update(self._thread_detail_panel(self._selected_thread()))
            return
        if self.selected_screen == "execution":
            inspector.update(self._execution_detail_panel())
            return
        if self.selected_screen == "overview":
            inspector.update(self._overview_detail_panel())
            return
        if self.selected_screen == "research":
            inspector.update(self._research_detail_panel())
            return
        inspector.update(self._future_detail_panel())

    def _render_command_status(self) -> None:
        status = self.query_one("#command_status", Static)
        if self.pending_action is not None:
            lines = [
                Text("PENDING ACTION", style="bold yellow"),
                Text(f"summary: {self.pending_action.summary}", style="white"),
                Text(f"target: {self.pending_action.target}", style="grey70"),
                Text(f"expected: {self.pending_action.expected_result}", style="grey70"),
                Text(f"verify: {self.pending_action.verify_command}", style="cyan"),
                Text("press Enter to confirm, Esc to cancel", style="grey62"),
            ]
            status.update(Panel(Group(*lines), border_style="yellow", title="COMMAND BAR"))
            return

        lines = [Text("COMMAND BAR", style="bold white")]
        if self.command_message:
            lines.append(Text(self.command_message, style="cyan"))
        hint = Text(self._shortcut_hint(), style="grey70")
        if self.error_message and self.snapshot is None:
            hint = Text(f"connection error: {_shorten(self.error_message, width=120)}", style="bold red")
        lines.extend([Text(" "), hint])
        status.update(Panel(Group(*lines), border_style="grey35"))

    def _shortcut_hint(self) -> str:
        if self.help_visible:
            return "help open: press ? again to close"
        if self.selected_screen == "threads":
            return "s start/resume   p pause   x stop   r restart   v verify   / command"
        if self.selected_screen == "execution":
            return "s start control   p pause control   x stop control   r restart   v verify   / command"
        if self.selected_screen == "research":
            return "r refresh   / command   tab cycle focus"
        return "j/k choose screen or item   r refresh   / command   ? help"

    def _selected_thread(self) -> dict[str, Any] | None:
        if self.snapshot is None:
            return None
        return self.snapshot.experiment_at(self.selected_thread_index)

    def _selected_event(self) -> dict[str, Any] | None:
        if self.snapshot is None or not self.snapshot.events:
            return None
        return self.snapshot.events[self.selected_event_index % len(self.snapshot.events)]

    def _selected_position(self) -> dict[str, Any] | None:
        if self.snapshot is None:
            return None
        positions = self.snapshot.paper.get("positions") or []
        if not isinstance(positions, list) or not positions:
            return None
        item = positions[self.selected_position_index % len(positions)]
        return item if isinstance(item, dict) else None

    def _verification_command(self, *, target: str, action: str, experiment_id: str | None = None) -> str:
        base = self.client.base_url
        snippet = [
            "uv run python -c \"import requests;",
            f"d=requests.get('{base}/api/dashboard', timeout=5).json();",
        ]
        if target == "paper":
            snippet.append("print(d['paper']['running'], d['paper']['engine'].get('equity'))\"")
        elif target == "experiment":
            snippet.append(
                f"print(next((x for x in d['experiments'] if x.get('id')=='{experiment_id}'), {{}}).get('health'))\""
            )
        elif target == "experiment-manager":
            snippet.append("print(d['workbench']['experiment_manager']['summary']['manager_state'])\"")
        else:
            snippet.append("print(d['workbench']['experiment_manager']['summary']['leader_id'])\"")
        return "".join(snippet)

    def _build_kv(self, rows: list[tuple[str, Any]]) -> Table:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="grey70", width=16)
        table.add_column(style="white", ratio=1)
        for label, value in rows:
            table.add_row(f"{label}:", str(value))
        return table

    def _overview_action(self) -> ActionPreview | None:
        if self.snapshot is None:
            return None
        action = self.snapshot.actions[0] if self.snapshot.actions else None
        if not action:
            return ActionPreview(
                summary="Refresh the workbench snapshot",
                target="dashboard snapshot",
                expected_result="The top bar and mission pane should update with the latest /api/dashboard state.",
                verify_command=self._verification_command(target="overview", action="refresh"),
                payload={"target": "dashboard", "action": "refresh"},
            )
        title = str(action.get("title") or "recommended action")
        detail = str(action.get("detail") or "")
        return ActionPreview(
            summary=title,
            target="overview recommendation",
            expected_result=_shorten(detail or "The operator guidance should remain visible in the overview pane.", width=110),
            verify_command=self._verification_command(target="overview", action="refresh"),
            payload={"target": "dashboard", "action": "refresh"},
        )

    def _overview_detail_panel(self) -> Panel:
        assert self.snapshot is not None
        leader = self.snapshot.leader_experiment()
        event = self._selected_event()
        action = self._overview_action()
        rows = [
            ("leader", leader.get("id") if leader else self.snapshot.leader_id or "n/a"),
            ("leader score", _format_number(self.snapshot.leader_score, precision=3)),
            ("paper equity", _format_currency(self.snapshot.paper_equity)),
            ("active", self.snapshot.active_count),
            ("degraded", self.snapshot.degraded_count),
            ("failed", self.snapshot.failed_count),
        ]
        blocks: list[Any] = [Text("ROOM SUMMARY", style="bold white"), self._build_kv(rows)]
        if action is not None:
            blocks.extend([Text(" "), Text("NEXT ACTION", style="bold white"), Text(action.summary, style="yellow"), Text(action.verify_command, style="cyan")])
        if event is not None:
            blocks.extend(
                [
                    Text(" "),
                    Text("LATEST EVENT", style="bold white"),
                    Text(f"{_format_timestamp(event.get('timestamp'))}  {event.get('type')}  {event.get('experiment_id') or 'n/a'}", style="grey70"),
                ]
            )
        return Panel(Group(*blocks), border_style="green", title="OVERVIEW")

    def _thread_detail_panel(self, item: dict[str, Any] | None) -> Panel:
        if item is None:
            return Panel(Text("No experiment selected.", style="grey62"), border_style="grey35", title="THREAD")
        rows = [
            ("id", item.get("id")),
            ("state", item.get("state")),
            ("health", item.get("health")),
            ("phase", item.get("phase")),
            ("phase detail", item.get("phase_detail")),
            ("desired", item.get("desired_state")),
            ("best score", _format_number(item.get("best_score"), precision=3)),
            ("iteration", _format_number(item.get("iteration"), precision=0)),
            ("last decision", (item.get("last_decision") or {}).get("status")),
            ("last error", _shorten(item.get("last_error"), width=70)),
            ("reasons", ", ".join(item.get("health_reasons") or []) or "none"),
        ]
        blocks: list[Any] = [Text("THREAD DETAIL", style="bold white"), self._build_kv(rows)]
        if item.get("last_metrics"):
            blocks.extend([Text(" "), Text("LAST METRICS", style="bold white"), Text(_shorten(json.dumps(item.get("last_metrics"), sort_keys=True), width=100), style="grey62")])
        if item.get("last_verification"):
            blocks.extend([Text(" "), Text("VERIFY", style="bold white"), Text(_shorten(json.dumps(item.get("last_verification"), sort_keys=True), width=100), style="grey62")])
        return Panel(Group(*blocks), border_style=_style_for_health(str(item.get("health") or "")), title="THREADS")

    def _execution_detail_panel(self) -> Panel:
        assert self.snapshot is not None
        rows = [
            ("paper", _yesno(self.snapshot.paper_running)),
            ("paper pid", self.snapshot.paper_pid),
            ("returncode", self.snapshot.paper_returncode),
            ("manager", self.snapshot.manager_state),
            ("manager pid", self.snapshot.manager_pid),
            ("positions", len(self.snapshot.paper.get("positions") or [])),
        ]
        blocks: list[Any] = [Text("EXECUTION DETAIL", style="bold white"), self._build_kv(rows)]
        position = self._selected_position()
        if position:
            blocks.extend([Text(" "), Text("POSITION", style="bold white"), Text(f"{position.get('symbol') or 'n/a'} {position.get('direction') or ''} {_format_currency(position.get('notional'))}", style="grey62")])
        blocks.extend(
            [
                Text(" "),
                Text("VERIFY COMMANDS", style="bold white"),
                Text(self._verification_command(target="paper", action="refresh"), style="cyan"),
                Text(self._verification_command(target="experiment-manager", action="refresh"), style="cyan"),
            ]
        )
        return Panel(Group(*blocks), border_style="yellow", title="EXECUTION")

    def _research_detail_panel(self) -> Panel:
        assert self.snapshot is not None
        research = self.snapshot.research
        summary = research.get("summary") or {}
        counts = research.get("status_counts") or {}
        rows = [
            ("total runs", summary.get("total_runs")),
            ("best val bpb", _format_number(summary.get("best_val_bpb"), precision=3)),
            ("best commit", summary.get("best_commit")),
            ("keep", counts.get("keep")),
            ("discard", counts.get("discard")),
            ("crash", counts.get("crash")),
        ]
        commands = Table.grid(expand=True, padding=(0, 1))
        commands.add_column(style="grey70", width=18)
        commands.add_column(style="cyan", ratio=1)
        commands.add_row("backtest", "uv run backtest.py")
        commands.add_row("5m validate", "uv run python backtest_5m.py --split val --symbols SOL")
        commands.add_row("benchmarks", "uv run run_benchmarks.py")
        commands.add_row("equity export", "uv run python export_equity.py")
        blocks = [Text("RESEARCH SURFACE", style="bold white"), self._build_kv(rows), Text(" "), Text("ENTRYPOINTS", style="bold white"), commands]
        return Panel(Group(*blocks), border_style="grey35", title="RESEARCH")

    def _future_detail_panel(self) -> Panel:
        blocks = [
            Text("FUTURE SLOT", style="bold white"),
            Text(" "),
            Text("This lane is reserved for wallet, reports, and system surfaces in the next wave.", style="grey62"),
            Text(" "),
            Text("Capabilities remain explicit but inactive so the IA does not collapse later.", style="grey62"),
        ]
        return Panel(Group(*blocks), border_style="grey35", title="FUTURE")

    def _render_overview(self) -> Panel:
        assert self.snapshot is not None
        leader = self.snapshot.leader_experiment()
        action = self._overview_action()
        cards = Columns(
            [
                Panel(
                    Group(
                        Text("LEADER", style="bold white"),
                        Text(leader.get("id") if leader else self.snapshot.leader_id or "n/a", style="green"),
                        Text(f"score {_format_number(self.snapshot.leader_score, precision=3)}", style="grey70"),
                    ),
                    border_style="green",
                ),
                Panel(
                    Group(
                        Text("EQUITY", style="bold white"),
                        Text(_format_currency(self.snapshot.paper_equity), style="green"),
                        Text(f"paper {_yesno(self.snapshot.paper_running)}", style="grey70"),
                    ),
                    border_style="green" if self.snapshot.paper_running else "yellow",
                ),
                Panel(
                    Group(
                        Text("HEALTH", style="bold white"),
                        Text(f"active {self.snapshot.active_count}", style="green"),
                        Text(f"degraded {self.snapshot.degraded_count}", style="yellow"),
                        Text(f"failed {self.snapshot.failed_count}", style="red"),
                    ),
                    border_style="yellow" if self.snapshot.degraded_count or self.snapshot.failed_count else "green",
                ),
            ],
            equal=True,
            expand=True,
        )
        event_table = Table(title="RECENT EVENTS", expand=True, box=None, pad_edge=False)
        event_table.add_column("time", style="grey70", width=11)
        event_table.add_column("type", style="white", width=20)
        event_table.add_column("id", style="cyan", width=18)
        event_table.add_column("detail", style="grey62", ratio=1)
        for event in self.snapshot.events[-5:]:
            payload = event.get("payload") or {}
            detail = payload.get("phase") or payload.get("reason") or payload.get("search_space") or ""
            event_table.add_row(
                _format_timestamp(event.get("timestamp")),
                str(event.get("type") or "n/a"),
                str(event.get("experiment_id") or "n/a"),
                _shorten(detail or json.dumps(payload, sort_keys=True), width=80),
            )
        action_panel = Panel(
            Group(
                Text("RECOMMENDED ACTION", style="bold white"),
                Text(action.summary if action else "n/a", style="yellow"),
                Text(action.expected_result if action else "No action available.", style="grey70"),
                Text(action.verify_command if action else "n/a", style="cyan"),
            ),
            border_style="yellow",
            title="NEXT",
        )
        return Panel(
            Group(Text("OVERVIEW", style="bold white"), Text(" "), cards, Text(" "), action_panel, Text(" "), event_table),
            border_style="green",
            title="OVERVIEW",
        )

    def _render_threads(self) -> Panel:
        assert self.snapshot is not None
        table = Table(title="THREAD FLEET", expand=True)
        table.add_column("#", width=3, justify="right")
        table.add_column("id", style="white", width=22)
        table.add_column("state", width=10)
        table.add_column("health", width=10)
        table.add_column("phase", width=18)
        table.add_column("score", width=9, justify="right")
        table.add_column("delta", width=9, justify="right")
        table.add_column("reasons", style="grey62", ratio=1)
        for idx, item in enumerate(self.snapshot.experiments[:10]):
            selected = idx == self.selected_thread_index % max(1, len(self.snapshot.experiments))
            prefix = ">" if selected else str(idx + 1)
            state = str(item.get("state") or "n/a")
            health = str(item.get("health") or "n/a")
            last_decision = item.get("last_decision") or {}
            candidate_score = (item.get("last_metrics") or {}).get("score")
            delta = last_decision.get("score_delta")
            reasons = ", ".join(item.get("health_reasons") or []) or "none"
            row_style = _style_for_health(health) if selected else None
            table.add_row(
                prefix,
                _shorten(item.get("id"), width=22),
                Text(state, style=_style_for_state(state)),
                Text(health, style=_style_for_health(health)),
                _shorten(item.get("phase"), width=18),
                _format_number(candidate_score, precision=3),
                _format_signed(delta),
                _shorten(reasons, width=42),
                style=row_style,
            )
        return Panel(
            Group(
                Text("THREADS", style="bold white"),
                Text(" "),
                table,
                Text(" "),
                Text(self._thread_actions_text(), style="grey70"),
            ),
            border_style="yellow" if self.snapshot.degraded_count or self.snapshot.failed_count else "green",
            title="THREADS",
        )

    def _render_execution(self) -> Panel:
        assert self.snapshot is not None
        readiness = Columns(
            [
                Panel(
                    Group(
                        Text("PAPER FEED", style="bold white"),
                        Text(_yesno(self.snapshot.paper_running), style=_style_for_state("running" if self.snapshot.paper_running else "stopped")),
                        Text(f"pid {_format_number(self.snapshot.paper_pid, precision=0)}", style="grey70"),
                        Text(f"returncode {_format_number(self.snapshot.paper_returncode, precision=0)}", style="grey70"),
                    ),
                    border_style="green" if self.snapshot.paper_running else "yellow",
                ),
                Panel(
                    Group(
                        Text("MANAGER", style="bold white"),
                        Text(self.snapshot.manager_state, style=_style_for_state(self.snapshot.manager_state)),
                        Text(f"pid {_format_number(self.snapshot.manager_pid, precision=0)}", style="grey70"),
                        Text(f"leader {self.snapshot.leader_id or 'n/a'}", style="grey70"),
                    ),
                    border_style=_style_for_state(self.snapshot.manager_state),
                ),
                Panel(
                    Group(Text("POSITIONS", style="bold white"), Text(str(len(self.snapshot.paper.get("positions") or [])), style="green"), Text("wallet lane inactive", style="grey62")),
                    border_style="grey35",
                ),
            ],
            equal=True,
            expand=True,
        )
        positions = Table(title="CURRENT POSITIONS", expand=True)
        positions.add_column("symbol", style="white")
        positions.add_column("direction", style="grey70")
        positions.add_column("notional", justify="right")
        positions.add_column("entry", justify="right")
        for idx, item in enumerate((self.snapshot.paper.get("positions") or [])[:8]):
            if not isinstance(item, dict):
                continue
            selected = idx == self.selected_position_index % max(1, len(self.snapshot.paper.get("positions") or [1]))
            positions.add_row(
                str(item.get("symbol") or "n/a"),
                str(item.get("direction") or "n/a"),
                _format_currency(item.get("notional")),
                _format_currency(item.get("entry_price")),
                style="bold white" if selected else None,
            )
        verify = Table.grid(expand=True)
        verify.add_column(style="grey70", width=20)
        verify.add_column(style="cyan", ratio=1)
        verify.add_row("paper verify", self._verification_command(target="paper", action="refresh"))
        verify.add_row("manager verify", self._verification_command(target="experiment-manager", action="refresh"))
        return Panel(
            Group(Text("EXECUTION", style="bold white"), Text(" "), readiness, Text(" "), positions, Text(" "), Text("VERIFY", style="bold white"), verify),
            border_style="yellow" if self.snapshot.degraded_count or not self.snapshot.paper_running else "green",
            title="EXECUTION",
        )

    def _render_research(self) -> Panel:
        assert self.snapshot is not None
        research = self.snapshot.research
        summary = research.get("summary") or {}
        counts = research.get("status_counts") or {}
        rows = [
            ("total runs", summary.get("total_runs")),
            ("best val bpb", _format_number(summary.get("best_val_bpb"), precision=3)),
            ("best commit", summary.get("best_commit")),
            ("keep", counts.get("keep")),
            ("discard", counts.get("discard")),
            ("crash", counts.get("crash")),
        ]
        commands = Table.grid(expand=True, padding=(0, 1))
        commands.add_column(style="grey70", width=18)
        commands.add_column(style="cyan", ratio=1)
        commands.add_row("backtest", "uv run backtest.py")
        commands.add_row("5m validate", "uv run python backtest_5m.py --split val --symbols SOL")
        commands.add_row("benchmarks", "uv run run_benchmarks.py")
        commands.add_row("equity export", "uv run python export_equity.py")
        return Panel(
            Group(Text("RESEARCH SURFACE", style="bold white"), self._build_kv(rows), Text(" "), Text("ENTRYPOINTS", style="bold white"), commands),
            border_style="grey35",
            title="RESEARCH",
        )

    def _render_future_slot(self) -> Panel:
        return Panel(
            Group(
                Text("FUTURE SLOT", style="bold white"),
                Text(" "),
                Text("This lane is reserved for wallet, reports, and system surfaces in the next wave.", style="grey62"),
                Text(" "),
                Text("Capabilities remain explicit but inactive so the IA does not collapse later.", style="grey62"),
            ),
            border_style="grey35",
            title="FUTURE",
        )

    def _render_help_panel(self) -> Panel:
        help_table = Table.grid(expand=True, padding=(0, 1))
        help_table.add_column(style="grey70", width=18)
        help_table.add_column(style="white", ratio=1)
        for key, value in [
            ("j/k or arrows", "move through the current list or screen rail"),
            ("tab", "cycle nav, mission, inspector, command"),
            ("/", "focus the command bar"),
            ("r", "refresh /api/dashboard"),
            ("s", "stage a start or resume action"),
            ("p", "stage a pause action"),
            ("x", "stage a stop action"),
            ("v", "stage the verification command for the current target"),
            ("?", "toggle this help"),
        ]:
            help_table.add_row(key, value)
        return Panel(
            Group(
                Text("SHORTCUTS", style="bold white"),
                Text(" "),
                help_table,
                Text(" "),
                Text("Mutations are staged first so the operator sees summary, target, expected result, and verify command before confirm.", style="grey62"),
            ),
            border_style="grey35",
            title="HELP",
        )

    def _thread_actions_text(self) -> str:
        item = self._selected_thread()
        if item is None:
            return "no thread selected"
        state = str(item.get("state") or "idle").lower()
        start_label = "resume" if state == "paused" else ("start" if state in {"idle", "stopped"} else "start/resume")
        return f"s {start_label}   p pause   x stop   r restart   v verify   / command"

    def _stage_action(self, preview: ActionPreview) -> None:
        self.pending_action = preview
        self.command_message = f"staged: {preview.summary}"
        self.focus_region = "main"
        command = self.query_one("#command_input", Input)
        command.value = ""
        command.blur()
        self._render_command_status()

    def _current_thread_action(self, action: str) -> ActionPreview | None:
        item = self._selected_thread()
        if item is None:
            return None
        experiment_id = str(item.get("id") or "").strip()
        if not experiment_id:
            return None
        state = str(item.get("state") or "idle").lower()
        if action == "start":
            verb = "resume" if state == "paused" else "start"
            summary = f"{verb.title()} thread {experiment_id}"
            expected = f"Experiment {experiment_id} should move toward a running cycle and report fresh metrics."
        elif action == "pause":
            verb = "pause"
            summary = f"Pause thread {experiment_id}"
            expected = f"Experiment {experiment_id} should enter the paused state and stop launching new cycles."
        elif action == "stop":
            verb = "stop"
            summary = f"Stop thread {experiment_id}"
            expected = f"Experiment {experiment_id} should stop and remain out of the active queue."
        elif action == "restart":
            verb = "restart"
            summary = f"Restart thread {experiment_id}"
            expected = f"Experiment {experiment_id} should restart from the current control state with a fresh nonce."
        else:
            return None
        return ActionPreview(
            summary=summary,
            target=f"experiment {experiment_id}",
            expected_result=expected,
            verify_command=self._verification_command(target="experiment", action=verb, experiment_id=experiment_id),
            payload={"target": "experiment", "action": verb, "experiment_id": experiment_id},
        )

    def _execution_action(self, action: str) -> ActionPreview | None:
        if self.snapshot is None:
            return None
        paper_running = self.snapshot.paper_running
        if action == "start":
            if not paper_running:
                target = "paper"
                verb = "start"
                summary = "Start paper engine"
                expected = "Paper replay should start and the top bar should show a running paper feed."
            else:
                target = "experiment-manager"
                verb = "start"
                summary = "Start experiment manager"
                expected = "Experiment manager should be running and the thread fleet should continue cycling."
        elif action == "pause":
            target = "experiment-manager"
            verb = "pause"
            summary = "Pause experiment manager"
            expected = "Manager should enter the paused state and stop scheduling new work."
        elif action == "stop":
            target = "paper"
            verb = "stop"
            summary = "Stop paper engine"
            expected = "Paper feed should stop and the snapshot should show a stopped paper process."
        elif action == "restart":
            target = "paper"
            verb = "restart"
            summary = "Restart paper engine"
            expected = "Paper feed should restart and report a new live snapshot."
        else:
            return None
        return ActionPreview(
            summary=summary,
            target=target,
            expected_result=expected,
            verify_command=self._verification_command(target=target, action=verb),
            payload={"target": target, "action": verb},
        )

    def action_refresh(self) -> None:
        asyncio.create_task(self.refresh_dashboard())

    def action_cycle_focus(self) -> None:
        regions = ["nav", "main", "inspector", "command"]
        index = regions.index(self.focus_region) if self.focus_region in regions else 0
        self.focus_region = regions[(index + 1) % len(regions)]
        command = self.query_one("#command_input", Input)
        if self.focus_region == "command":
            command.focus()
        else:
            command.blur()
        self.command_message = f"focus: {self.focus_region}"
        self._render_command_status()

    def action_focus_command(self) -> None:
        self.focus_region = "command"
        self.query_one("#command_input", Input).focus()
        self.command_message = "command bar focused"
        self._render_command_status()

    def action_focus_filter(self) -> None:
        command = self.query_one("#command_input", Input)
        command.value = "filter "
        command.focus()
        self.focus_region = "command"
        self.command_message = "type a filter term"
        self._render_command_status()

    def action_toggle_help(self) -> None:
        self.help_visible = not self.help_visible
        self.command_message = "help toggled"
        self._render_all()

    def action_cancel_pending(self) -> None:
        self.pending_action = None
        self.command_message = "pending action cancelled"
        self._render_command_status()

    def action_move_down(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen == "threads" and self.snapshot.experiments:
            self.selected_thread_index = (self.selected_thread_index + 1) % len(self.snapshot.experiments)
        elif self.selected_screen == "overview" and self.snapshot.events:
            self.selected_event_index = (self.selected_event_index + 1) % len(self.snapshot.events)
        elif self.selected_screen == "execution":
            positions = self.snapshot.paper.get("positions") or []
            if isinstance(positions, list) and positions:
                self.selected_position_index = (self.selected_position_index + 1) % len(positions)
        else:
            self._advance_screen(1)
            return
        self._render_all()

    def action_move_up(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen == "threads" and self.snapshot.experiments:
            self.selected_thread_index = (self.selected_thread_index - 1) % len(self.snapshot.experiments)
        elif self.selected_screen == "overview" and self.snapshot.events:
            self.selected_event_index = (self.selected_event_index - 1) % len(self.snapshot.events)
        elif self.selected_screen == "execution":
            positions = self.snapshot.paper.get("positions") or []
            if isinstance(positions, list) and positions:
                self.selected_position_index = (self.selected_position_index - 1) % len(positions)
        else:
            self._advance_screen(-1)
            return
        self._render_all()

    def _advance_screen(self, direction: int) -> None:
        screens = [slot for slot, _, _ in SCREEN_SLOTS]
        if self.selected_screen not in screens:
            self.selected_screen = "overview"
            return
        index = screens.index(self.selected_screen)
        self.selected_screen = screens[(index + direction) % len(screens)]
        self.command_message = f"screen: {self.selected_screen}"
        self._render_all()

    def action_stage_primary(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen == "threads":
            preview = self._current_thread_action("start")
        elif self.selected_screen == "execution":
            preview = self._execution_action("start")
        elif not self.snapshot.paper_running:
            preview = ActionPreview(
                summary="Start paper engine",
                target="paper",
                expected_result="Paper replay should start and the top bar should show a running paper feed.",
                verify_command=self._verification_command(target="paper", action="start"),
                payload={"target": "paper", "action": "start"},
            )
        elif self.snapshot.manager_state.lower() != "running":
            preview = ActionPreview(
                summary="Start experiment manager",
                target="experiment-manager",
                expected_result="Experiment manager should resume scheduling threads on the next refresh.",
                verify_command=self._verification_command(target="experiment-manager", action="start"),
                payload={"target": "experiment-manager", "action": "start"},
            )
        else:
            preview = self._overview_action()
        if preview is not None:
            self._stage_action(preview)

    def action_stage_pause(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen == "threads":
            preview = self._current_thread_action("pause")
        elif self.selected_screen == "execution":
            preview = self._execution_action("pause")
        else:
            preview = ActionPreview(
                summary="Pause experiment manager",
                target="experiment-manager",
                expected_result="Experiment manager should enter the paused state and stop scheduling new work.",
                verify_command=self._verification_command(target="experiment-manager", action="pause"),
                payload={"target": "experiment-manager", "action": "pause"},
            )
        if preview is not None:
            self._stage_action(preview)

    def action_stage_stop(self) -> None:
        if self.snapshot is None:
            return
        if self.selected_screen == "threads":
            preview = self._current_thread_action("stop")
        elif self.selected_screen == "execution":
            preview = self._execution_action("stop")
        else:
            preview = ActionPreview(
                summary="Stop paper engine",
                target="paper",
                expected_result="Paper feed should stop and the snapshot should show a stopped paper process.",
                verify_command=self._verification_command(target="paper", action="stop"),
                payload={"target": "paper", "action": "stop"},
            )
        if preview is not None:
            self._stage_action(preview)

    def action_show_verify(self) -> None:
        if self.pending_action is not None:
            self.command_message = self.pending_action.verify_command
            self._render_command_status()
            return
        preview = self._current_thread_action("restart") if self.selected_screen == "threads" else self._execution_action("restart") if self.selected_screen == "execution" else self._overview_action()
        if preview is not None:
            self._stage_action(preview)

    def action_confirm_pending(self) -> None:
        if self.pending_action is None:
            return
        payload = self.pending_action.payload
        self.command_message = f"dispatching {self.pending_action.summary}"
        self._render_command_status()
        asyncio.create_task(self._execute_pending_action(payload))

    async def _execute_pending_action(self, payload: dict[str, Any]) -> None:
        try:
            response = await asyncio.to_thread(self.client.control, payload)
        except Exception as exc:  # noqa: BLE001
            self.command_message = f"control failed: {exc}"
            self.pending_action = None
            self._render_command_status()
            return
        self.command_history.append(json.dumps(payload, sort_keys=True))
        self.pending_action = None
        self.command_message = f"control ok: {response.get('ok', False)}"
        self._render_command_status()
        await self.refresh_dashboard()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command_input":
            return
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        self.command_history.append(command)
        self.command_message = command
        self._render_command_status()
        if command in {"refresh", "r"}:
            self.action_refresh()
            return
        if command in {"help", "?"}:
            self.action_toggle_help()
            return
        if command.startswith("screen "):
            screen = command.split(" ", 1)[1].strip().lower()
            if screen in {slot for slot, _, _ in SCREEN_SLOTS}:
                self.selected_screen = screen
                self.command_message = f"screen: {self.selected_screen}"
                self._render_all()
            return
        if command.startswith("select thread "):
            value = command.rsplit(" ", 1)[-1]
            if value.isdigit() and self.snapshot and self.snapshot.experiments:
                self.selected_thread_index = int(value) - 1
                self.selected_screen = "threads"
                self.command_message = f"thread: {value}"
                self._render_all()
            return
        if command.startswith("start "):
            self._handle_command_action("start", command)
            return
        if command.startswith("pause "):
            self._handle_command_action("pause", command)
            return
        if command.startswith("stop "):
            self._handle_command_action("stop", command)
            return
        if command.startswith("restart "):
            self._handle_command_action("restart", command)
            return
        self.command_message = f"unknown command: {command}"
        self._render_command_status()

    def _handle_command_action(self, verb: str, command: str) -> None:
        parts = command.split()
        if len(parts) < 2:
            self.command_message = f"missing target: {command}"
            self._render_command_status()
            return
        target = parts[1].lower()
        if target == "paper":
            preview = ActionPreview(
                summary=f"{verb.title()} paper",
                target="paper",
                expected_result="Paper state should change on the next refresh.",
                verify_command=self._verification_command(target="paper", action=verb),
                payload={"target": "paper", "action": verb},
            )
        elif target in {"manager", "experiment-manager", "trainer"}:
            preview = ActionPreview(
                summary=f"{verb.title()} manager",
                target="experiment-manager",
                expected_result="Experiment manager should change on the next refresh.",
                verify_command=self._verification_command(target="experiment-manager", action=verb),
                payload={"target": "experiment-manager", "action": verb},
            )
        elif target == "thread" and len(parts) >= 3:
            thread_id = parts[2]
            preview = ActionPreview(
                summary=f"{verb.title()} thread {thread_id}",
                target=f"experiment {thread_id}",
                expected_result="Experiment should reflect the requested control action.",
                verify_command=self._verification_command(target="experiment", action=verb, experiment_id=thread_id),
                payload={"target": "experiment", "action": verb, "experiment_id": thread_id},
            )
        else:
            self.command_message = f"unknown target for command: {command}"
            self._render_command_status()
            return
        self._stage_action(preview)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto Research command-room TUI")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Workbench base URL")
    parser.add_argument("--refresh-seconds", type=float, default=DEFAULT_REFRESH_SECONDS, help="Refresh interval in seconds")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = AutoResearchTUI(
        base_url=args.base_url,
        refresh_seconds=args.refresh_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
