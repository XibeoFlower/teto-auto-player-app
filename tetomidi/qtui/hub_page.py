"""MIDI HUB page — bản Qt kính: danh sách bài hát của server, tìm kiếm, xem trước, tải về."""
from __future__ import annotations

import logging
import webbrowser
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..engine.transport import PAUSED, PLAYING, Transport
from ..hub import PAGE_SIZE, HubClient, HubError, HubSong, link_host
from ..midi_data import MidiLoadError, Song, format_time, load_song
from ..pianosound import PianoPreviewDispatcher, PianoSound
from ..rollmodel import build_roll
from .glassbtn import Badge, GlassButton, GlassSlider
from .roll import RollView
from .widgets import EllipsisLabel, PageTitle, ScrollArea, fit_text, make_h, make_v

log = logging.getLogger(__name__)

THUMB_W, THUMB_H, THUMB_R = 112, 63, 8
NOT_SET_UP = ("The MIDI Hub server is not set up yet.\n"
              "Put its address in HUB_API_URL (tetomidi/__init__.py) or in config.json as hub.apiUrl.")
ERR, WARN, MUTED, SOFT, GOOD = "#ff7b72", "#e0a13a", "#9c9ca4", "#e2e2e6", "#56bb6b"


def rounded_thumb(data: bytes, w: int, h: int, r: int) -> QPixmap | None:
    """Thumbnail bo góc từ dữ liệu ảnh (None nếu không đọc được)."""
    img = QImage.fromData(data)
    if img.isNull():
        return None
    scaled = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    from PySide6.QtCore import QRectF as _RF
    path.addRoundedRect(_RF(0, 0, w, h), r, r)
    p.setClipPath(path)
    p.drawImage((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
    p.end()
    return out


def placeholder_pixmap(w: int, h: int, r: int) -> QPixmap:
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtGui import QPainterPath, QColor
    from PySide6.QtCore import QRectF
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.fillPath(path, QColor(255, 255, 255, 26))
    p.setPen(Qt.PenStyle.NoPen)
    p.end()
    return out


class _Bridge(QObject):
    done = Signal(object)   # (kind, payload)


class HubRow(QWidget):
    """Một hàng bài hát trong danh sách (kính): thumbnail + tên + link + meta."""

    def __init__(self, song: HubSong, placeholder: QPixmap, on_open, parent=None):
        super().__init__(parent)
        self.song = song
        self.on_open = on_open
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._over = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 12, 10)
        lay.setSpacing(12)
        self.thumb = QLabel()
        self.thumb.setPixmap(placeholder)
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.thumb)
        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel(song.name)
        title.setObjectName("file")
        title.setWordWrap(True)
        info.addWidget(title)
        if song.source_url:
            link = QLabel(f"↗ {link_host(song.source_url)}")
            link.setObjectName("hint")
            link.setStyleSheet("color: #7884ff; background: transparent; text-decoration: underline;")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.mousePressEvent = lambda _e, url=song.source_url: webbrowser.open_new_tab(url)
            info.addWidget(link)
        else:
            none = QLabel("No original link")
            none.setObjectName("hint")
            info.addWidget(none)
        meta = " · ".join(p for p in (song.uploader, f"{song.size / 1024:.0f} KB" if song.size else "") if p)
        if meta:
            m = QLabel(meta)
            m.setObjectName("hint")
            info.addWidget(m)
        lay.addLayout(info, 1)

    def set_thumb(self, pm: QPixmap):
        self.thumb.setPixmap(pm)

    def enterEvent(self, e):
        self._over = True
        self.update()

    def leaveEvent(self, e):
        self._over = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._over = False
            self.update()
            cb = self.on_open
            if cb:
                cb(self.song)
            e.accept()


class HubPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app, self.cfg = app, app.cfg
        self.client = HubClient.from_config(self.cfg)
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tetomidi-hub")
        self._gen = 0
        self.songs: list[HubSong] = []
        self.total = 0
        self.query = ""
        self._loaded, self._loading = False, False
        self._thumbs: dict[int, QPixmap | None] = {}
        self._row_map: dict[int, HubRow] = {}
        self.current: HubSong | None = None
        self.song: Song | None = None
        self.local_path = None
        self.preview_sound = PianoSound(self.cfg)
        self.transport = Transport(PianoPreviewDispatcher(self.preview_sound, self.cfg), self.cfg)
        self._sound_open = False
        self.placeholder = placeholder_pixmap(THUMB_W, THUMB_H, THUMB_R)
        self._build()
        self._bridge = _Bridge()
        self._bridge.done.connect(self._on_bridge)
        self.cfg.on_change(self._on_cfg_change)

    # ------------------------------------------------------------ build
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 14, 24, 16)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.heading = PageTitle("MIDI HUB")
        head.addWidget(self.heading)
        self.search = _make_search(self._on_search)
        self.search.setFixedWidth(280)
        head.addWidget(self.search)
        refresh = GlassButton("↺")
        refresh.setObjectName("iconbtn")
        refresh.setToolTip("Reload the list")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        self.status = EllipsisLabel("", 12, MUTED)
        head.addWidget(self.status, 1)
        root.addLayout(head)

        # list + detail dùng chung một vùng: QStackedLayout thủ công qua hide/show
        self.list_view = QWidget()
        self.detail = QWidget()
        self._build_list(self.list_view)
        self._build_detail(self.detail)
        root.addWidget(self.list_view, 1)
        root.addWidget(self.detail, 1)
        self.detail.hide()
        self.list_view.show()

    def _build_list(self, host: QWidget):
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.scroll = ScrollArea()
        inner = QWidget()
        self.rows_lay = make_v(inner)
        self.rows_lay.setSpacing(8)
        self.rows_lay.addStretch()
        self.footer_btn = GlassButton("Load more")
        self.footer_btn.setObjectName("ghost")
        self.footer_btn.clicked.connect(self._load_more)
        self.footer_widget = QWidget()
        foot = QHBoxLayout(self.footer_widget)
        foot.setContentsMargins(0, 10, 0, 10)
        foot.addStretch()
        foot.addWidget(self.footer_btn)
        foot.addStretch()
        self.rows_lay.addWidget(self.footer_widget)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll)
        self.notice = QLabel("")
        self.notice.setObjectName("status")
        self.notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice.setWordWrap(True)
        self.notice.hide()
        self.retry_btn = GlassButton("Try again")
        self.retry_btn.setObjectName("ghost")
        self.retry_btn.clicked.connect(self.refresh)
        self.retry_btn.hide()
        lay.addWidget(self.notice)
        rrow = QHBoxLayout()
        rrow.addStretch()
        rrow.addWidget(self.retry_btn)
        rrow.addStretch()
        lay.addLayout(rrow)

    def _build_detail(self, host: QWidget):
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(12)
        back = GlassButton("Back")
        back.setObjectName("ghost")
        back.clicked.connect(self.show_list)
        top.addWidget(back)
        self.d_thumb = QLabel()
        self.d_thumb.setPixmap(self.placeholder)
        self.d_thumb.setFixedSize(THUMB_W, THUMB_H)
        top.addWidget(self.d_thumb)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.d_title = QLabel("")
        self.d_title.setObjectName("file")
        self.d_title.setWordWrap(True)
        info.addWidget(self.d_title)
        self.d_link = QLabel("")
        self.d_link.setObjectName("hint")
        self.d_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.d_link.mousePressEvent = lambda _e: self._open_source()
        info.addWidget(self.d_link)
        top.addLayout(info, 1)
        lay.addLayout(top)

        self.roll = RollView("piano", self.cfg)
        self.roll.setMinimumHeight(200)
        lay.addWidget(self.roll, 1)

        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.play_btn = GlassButton("PLAY")
        self.play_btn.setObjectName("play")
        self.play_btn.setFixedSize(96, 40)
        self.play_btn.clicked.connect(self.on_play)
        bar.addWidget(self.play_btn)
        self.stop_btn = GlassButton("STOP")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setFixedSize(96, 40)
        self.stop_btn.clicked.connect(self.on_stop)
        bar.addWidget(self.stop_btn)
        self.slider = GlassSlider(on_drag=self._on_slider_drag, on_commit=self._on_slider_commit)
        bar.addWidget(self.slider, 1)
        self.time = Badge(pill=True)
        self.time.setText("00:00:00/00:00:00")
        self.time.setFixedSize(190, 26)
        bar.addWidget(self.time)
        lay.addLayout(bar)

        acts = QHBoxLayout()
        acts.setSpacing(12)
        self.dl_btn = GlassButton("Download")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setToolTip("Save the .mid file in your Downloads folder")
        self.dl_btn.clicked.connect(self.download)
        acts.addWidget(self.dl_btn)
        self.use_btn = GlassButton("Open in Piano")
        self.use_btn.setObjectName("ghost")
        self.use_btn.setToolTip("Load the song into the Piano player (then play it with your hotkeys)")
        self.use_btn.clicked.connect(self.open_in_piano)
        acts.addWidget(self.use_btn)
        self.d_status = EllipsisLabel("", 12, MUTED)
        acts.addWidget(self.d_status, 1)
        lay.addLayout(acts)

    # ------------------------------------------------------ worker threads
    def _run(self, work, done, fail=None):
        """Chạy ``work()`` trên worker; kết quả trả về qua signal (thread-safe)."""
        bridge = self._bridge

        def job():
            try:
                result = work()
                payload = ("ok", done, result)
            except (HubError, MidiLoadError) as exc:
                payload = ("fail", fail, str(exc))
            except Exception as exc:
                log.exception("hub job failed")
                payload = ("fail", fail, f"Something went wrong ({exc.__class__.__name__}).")
            bridge.done.emit(payload)

        try:
            self.pool.submit(job)
        except RuntimeError:
            pass

    def _on_bridge(self, payload):
        kind, cb, result = payload
        if kind == "ok" and cb:
            cb(result)
        elif kind == "fail" and cb:
            cb(result)

    # ------------------------------------------------------------ the list
    def on_show(self):
        if not self._loaded and not self._loading:
            self._load(reset=True)

    def refresh(self):
        self._thumbs = {k: v for k, v in self._thumbs.items() if v}
        self.client = HubClient.from_config(self.cfg)
        self._load(reset=True)

    def _on_search(self, text: str):
        self.query = text
        if self.current is not None:
            self.show_list()
        self._load(reset=True)

    def _load_more(self):
        if not self._loading and len(self.songs) < self.total:
            self._load(reset=False)

    def _load(self, reset: bool):
        if not self.client.configured:
            self._clear_rows()
            self._show_notice(NOT_SET_UP, retry=False)
            self.status.set_text("")
            return
        self._gen += 1
        gen, query = self._gen, self.query
        offset = 0 if reset else len(self.songs)
        self._loading = True
        self.status.set_text("Searching" if query else "Loading", MUTED)
        self._run(lambda: self.client.list_songs(query, PAGE_SIZE, offset),
                  lambda res: self._on_loaded(gen, reset, res),
                  lambda msg: self._on_load_failed(gen, reset, msg))

    def _on_loaded(self, gen: int, reset: bool, result):
        if gen != self._gen:
            return
        songs, total = result
        self._loading, self._loaded = False, True
        if reset:
            self.songs = []
            self._clear_rows()
        self.songs += songs
        self.total = total
        self._hide_notice()
        self._render_new_rows()
        if not self.songs:
            self._show_notice(f'No songs found for "{self.query}".' if self.query else "The hub has no songs yet.",
                              retry=False)
            self.status.set_text("")
        else:
            self.status.set_text(f"{len(self.songs)} of {self.total} songs" if self.total > len(self.songs)
                                 else f"{self.total} song{'s' if self.total != 1 else ''}", MUTED)

    def _on_load_failed(self, gen: int, reset: bool, msg: str):
        if gen != self._gen:
            return
        self._loading = False
        self.status.set_text("")
        if reset:
            self.songs = []
            self._clear_rows()
            self._show_notice(msg, retry=True)
        else:
            self.status.set_text(msg, ERR)
            self._render_new_rows()

    def _show_notice(self, text: str, retry: bool):
        self.notice.setText(text)
        self.notice.show()
        self.retry_btn.setVisible(retry)

    def _hide_notice(self):
        self.notice.hide()
        self.retry_btn.hide()

    def _clear_rows(self):
        for row in list(self._row_map.values()):
            self.rows_lay.removeWidget(row)
            row.deleteLater()
        self._row_map.clear()
        self._rendered = 0

    def _render_new_rows(self):
        self.footer_widget.setVisible(self.total > len(self.songs))
        for song in self.songs[self._rendered:]:
            row = HubRow(song, self.placeholder, self.open_song)
            row.on_open = self.open_song
            # chèn trước stretch (phần tử cuối)
            self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
            self._row_map[song.id] = row
            self._ensure_thumb(song, row)
        self._rendered = len(self.songs)

    def _ensure_thumb(self, song: HubSong, row: HubRow):
        have = self._thumbs.get(song.id)
        if have:
            row.set_thumb(have)
            return
        if song.id in self._thumbs or not song.thumbnail_url:
            return

        def work():
            return rounded_thumb(self.client.thumbnail(song), THUMB_W, THUMB_H, THUMB_R)

        def done(pm):
            if pm is not None:
                self._thumbs[song.id] = pm
                r = self._row_map.get(song.id)
                if r is not None:
                    r.set_thumb(pm)
                if self.current is not None and self.current.id == song.id:
                    self.d_thumb.setPixmap(pm)

        self._run(work, done, lambda _m: None)

    # ------------------------------------------------------------- detail
    @property
    def detail_open(self) -> bool:
        return self.current is not None

    def open_song(self, song: HubSong):
        self._stop_preview()
        self.current, self.song, self.local_path = song, None, None
        self.d_title.setText(song.name)
        if song.source_url:
            self.d_link.setText(f"Original song: {link_host(song.source_url)}")
            self.d_link.setStyleSheet("color: #7884ff; background: transparent; text-decoration: underline;")
        else:
            self.d_link.setText("No original link")
            self.d_link.setStyleSheet("color: #6b6b74; background: transparent;")
        self.d_thumb.setPixmap(self._thumbs.get(song.id) or self.placeholder)
        if song.id not in self._thumbs:
            pass
        self.roll.set_data(build_roll("piano", None, self.cfg.data["piano"]))
        self.transport.load(None, 0.0)
        self._set_actions(False)
        self._set_status("Loading the song", MUTED)
        self.detail.show()
        self.list_view.hide()

        def work():
            path = self.client.midi_path(song)
            return path, load_song(str(path))

        self._run(work, lambda res: self._on_song_ready(song, *res), lambda msg: self._on_song_failed(song, msg))

    def _on_song_ready(self, song: HubSong, path, loaded: Song):
        if self.current is not song:
            return
        self.local_path, self.song = path, loaded
        self.transport.load(loaded.view("piano", bool(self.cfg.get("piano.skipPercussion", True))), loaded.length)
        self.rebuild_roll()
        self._set_actions(True)
        notes = len(self.transport.view.notes) if self.transport.view else 0
        self._set_status(f"{format_time(loaded.length)[3:]}  ·  {notes} notes", MUTED)

    def _on_song_failed(self, song: HubSong, msg: str):
        if self.current is song:
            self._set_status(f"⚠ {msg}", ERR)

    def show_list(self):
        self._stop_preview()
        self._close_sound()
        self.current, self.song = None, None
        self.detail.hide()
        self.list_view.show()

    def rebuild_roll(self):
        view = None
        if self.song:
            view = self.song.view("piano", bool(self.cfg.get("piano.skipPercussion", True)))
        self.roll.set_data(build_roll("piano", view, self.cfg.data["piano"]))

    def _set_actions(self, enabled: bool):
        for btn in (self.play_btn, self.stop_btn, self.dl_btn, self.use_btn):
            btn.setEnabled(enabled)
        self.slider.setEnabled(enabled)

    def _set_status(self, text: str, color: str):
        self.d_status.set_text(text, color)

    def _open_source(self):
        if self.current is not None and self.current.source_url:
            webbrowser.open_new_tab(self.current.source_url)

    # ------------------------------------------------------------ preview
    def _open_sound(self):
        if not self._sound_open:
            self.preview_sound.apply()
            self._sound_open = True
            if self.preview_sound.error:
                self._set_status(f"⚠ No sound: {self.preview_sound.error}", WARN)

    def _close_sound(self):
        if self._sound_open:
            self._sound_open = False
            self.preview_sound.close()

    def _stop_preview(self):
        if self.transport.state != "stopped":
            self.transport.stop()

    def on_play(self):
        if not self.song:
            return
        if self.transport.state == PLAYING:
            self.transport.pause()
        else:
            self._open_sound()
            self.transport.play()
        self.update_view()

    def on_hotkey_play(self):
        if self.detail_open and self.song and self.transport.state != PLAYING:
            self.on_play()

    def on_pause(self):
        if self.transport.state in (PLAYING, PAUSED):
            self.transport.toggle_pause()
        self.update_view()

    def on_stop(self):
        self._stop_preview()
        self.update_view()

    def change_speed(self, _delta):
        pass

    def leave(self):
        """The page is hidden: the preview must not keep playing."""
        self._stop_preview()
        self._close_sound()
        self.update_view()

    def _on_slider_drag(self, v):
        if self.song:
            self.time.setText(f"{format_time(v * self.song.length)}/{format_time(self.song.length)}")

    def _on_slider_commit(self, v):
        if self.song:
            self.transport.seek(v * self.song.length)

    def update_view(self):
        if not self.detail_open:
            return
        t = self.transport
        pos = t.position()
        t.consume_finished()
        self.roll.pos = pos
        self.roll.update()
        length = t.length if self.song else 0.0
        if not self.slider.dragging:
            self.slider.set_fraction(pos / length if length else 0.0)
            self.time.setText(f"{format_time(pos)}/{format_time(length)}")
        want = "PAUSE" if t.state == PLAYING else "PLAY"
        if self.play_btn.text() != want:
            self.play_btn.setText(want)
            self.play_btn.set_glass_kind("amber" if t.state == PLAYING else "green")

    # ------------------------------------------------------------ actions
    def download(self):
        song = self.current
        if song is None:
            return
        self.dl_btn.setEnabled(False)
        self._set_status("Saving the file", MUTED)

        def done(path):
            self.dl_btn.setEnabled(self.song is not None)
            if self.current is song:
                self._set_status(f"Saved: {path}", GOOD)

        def fail(msg):
            self.dl_btn.setEnabled(self.song is not None)
            if self.current is song:
                self._set_status(f"⚠ {msg}", ERR)

        self._run(lambda: self.client.download(song), done, fail)

    def open_in_piano(self):
        if self.local_path is None:
            return
        piano = self.app.pages["piano"]
        if piano.load_path(str(self.local_path)):
            self.app.show_page("piano")

    # ------------------------------------------------------------- config
    def _on_cfg_change(self, path: str):
        if path == "*" or path == "hub.apiUrl":
            self.client = HubClient.from_config(self.cfg)
            self._loaded = False
        if path == "*" or path.startswith("piano."):
            rest = path[len("piano."):] if path.startswith("piano.") else ""
            if path == "*" or rest.split(".")[0] in ("88Keys", "pitchOffset", "transposeOffset",
                                                    "skipPercussion", "velocity", "noteLengths", "pianoMap"):
                self.rebuild_roll()
        elif path.startswith("roll."):
            self.roll.refresh_style()

    def shutdown(self):
        try:
            self.transport.stop()
        except Exception:
            log.exception("stopping the preview")
        self.preview_sound.close()
        self.pool.shutdown(wait=False, cancel_futures=True)


def _make_search(on_search):
    from .widgets import SearchBox
    return SearchBox(on_search)
