import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
TOOLS = ROOT / 'tools'
CREATE_FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def normalize_url(value):
    value = value.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('https', 'http'):
        raise ValueError('https://로 시작하는 YouTube 영상 링크를 입력하세요.')
    if host == 'youtu.be':
        video_id = parsed.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        parts = parsed.path.strip('/').split('/')
        video_id = parse_qs(parsed.query).get('v', [''])[0] if parsed.path == '/watch' else (parts[1] if len(parts) == 2 and parts[0] in ('shorts', 'live', 'embed') else '')
    else:
        raise ValueError('YouTube 영상 링크만 지원합니다.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('영상 ID를 확인할 수 없습니다. 영상의 공유 링크를 복사하세요.')
    return 'https://www.youtube.com/watch?v=' + video_id


def selector(height=None):
    limit = f'[height<={int(height)}]' if height else ''
    return f'bv{limit}+ba/b{limit}'


def emit(kind, **data):
    print(json.dumps(dict(kind=kind, **data), ensure_ascii=False), flush=True)


def worker(action, url, folder='', height=''):
    import yt_dlp

    class Logger:
        def debug(self, msg):
            pass
        def warning(self, msg):
            emit('warning', text=msg)
        def error(self, msg):
            pass

    options = dict(quiet=True, no_warnings=False, logger=Logger(), noplaylist=True,
                   socket_timeout=25, retries=3, windowsfilenames=True,
                   js_runtimes={'node': {'path': str(TOOLS / 'node.exe')}},
                   ffmpeg_location=str(TOOLS), cachedir=False)
    if action == 'info':
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        if info.get('is_live'):
            raise ValueError('진행 중인 라이브 방송은 지원하지 않습니다.')
        heights = sorted({int(f['height']) for f in info.get('formats', [])
                          if f.get('height') and f.get('vcodec') != 'none' and not f.get('has_drm')}, reverse=True)
        emit('info', title=info.get('title', ''), duration=info.get('duration', 0), heights=heights)
        return

    def progress(data):
        if data['status'] == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            emit('progress', percent=min(99, data.get('downloaded_bytes', 0) / total * 100) if total else 0,
                 speed=data.get('speed'), eta=data.get('eta'), filename=Path(data.get('filename', '')).name)
        elif data['status'] == 'finished':
            emit('status', text='다운로드 단계 완료 · 다음 트랙 또는 영상·음성 병합 준비 중')

    def post(data):
        emit('status', text='영상·음성 병합 및 파일 정리 중…')

    options.update(format=selector(height or None), outtmpl=str(Path(folder) / '%(title).150B [%(id)s].%(ext)s'),
                   merge_output_format='mp4/mkv', overwrites=False,
                   progress_hooks=[progress], postprocessor_hooks=[post])
    Path(folder).mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get('is_live'):
            raise ValueError('진행 중인 라이브 방송은 지원하지 않습니다.')
        vid = info['id']
        existing = [p for p in Path(folder).iterdir() if p.is_file() and f'[{vid}]' in p.name and p.suffix in ('.mp4', '.mkv', '.webm') and not re.search(r'\.f\d+\.', p.name)]
        if existing:
            raise ValueError('이 영상의 완료 파일이 저장 폴더에 이미 있습니다. 다른 폴더를 선택하세요.')
        result = ydl.process_ie_result(info, download=True)
        filename = result.get('filepath') or ydl.prepare_filename(result)
        paths = [p for p in Path(folder).iterdir() if p.is_file() and f'[{vid}]' in p.name and p.suffix in ('.mp4', '.mkv', '.webm') and not re.search(r'\.f\d+\.', p.name)]
        if paths:
            filename = str(max(paths, key=lambda p: p.stat().st_mtime))
        if not Path(filename).is_file():
            raise RuntimeError('완료 파일을 확인하지 못했습니다. 저장 폴더를 확인하세요.')
        emit('done', path=filename)


def main():
    if getattr(sys, 'frozen', False):
        import ctypes
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title('YouTube 고화질 다운로드')
    root.geometry('780x580')
    root.minsize(700, 540)
    root.configure(bg='#f3f5f9')
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('맑은 고딕', 10))
    style.configure('TFrame', background='#f3f5f9')
    style.configure('TLabel', background='#f3f5f9', foreground='#202b40')
    style.configure('Title.TLabel', font=('맑은 고딕', 22, 'bold'))
    style.configure('TButton', padding=(12, 8))
    style.configure('Accent.TButton', background='#2563eb', foreground='white')
    style.map('Accent.TButton', background=[('active', '#1d4ed8'), ('disabled', '#a0aec0')])
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text='YouTube 고화질 다운로드', style='Title.TLabel').grid(row=0, sticky='w')
    ttk.Label(frame, text='링크를 확인하고 원본에서 제공하는 화질로 저장하세요.').grid(row=1, sticky='w', pady=(5, 22))
    url = tk.StringVar(value='https://youtu.be/dMFNkCkOOrU')
    folder = tk.StringVar(value=str(Path.home() / 'Downloads'))
    quality = tk.StringVar(value='최고 화질 자동')
    title = tk.StringVar(value='영상 링크를 넣고 [영상 확인]을 누르세요.')
    status = tk.StringVar(value='준비됨')
    detail = tk.StringVar(value='진행률은 현재 영상·음성 트랙 기준입니다.')
    progress = tk.DoubleVar(value=0)
    events = queue.Queue()
    state = {'process': None, 'busy': False, 'checked': None, 'cancelled': False, 'done': False}
    ttk.Label(frame, text='영상 링크').grid(row=2, sticky='w')
    line = ttk.Frame(frame)
    line.grid(row=3, sticky='ew', pady=(6, 14))
    line.columnconfigure(0, weight=1)
    entry = ttk.Entry(line, textvariable=url, font=('맑은 고딕', 11))
    entry.grid(row=0, column=0, sticky='ew', ipady=7, padx=(0, 10))
    check = ttk.Button(line, text='영상 확인')
    check.grid(row=0, column=1)
    ttk.Label(frame, textvariable=title, wraplength=710, font=('맑은 고딕', 11, 'bold')).grid(row=4, sticky='w', pady=(0, 14))
    ttk.Label(frame, text='화질').grid(row=5, sticky='w')
    combo = ttk.Combobox(frame, textvariable=quality, values=['최고 화질 자동'], state='readonly')
    combo.grid(row=6, sticky='ew', pady=(6, 14))
    ttk.Label(frame, text='저장 폴더').grid(row=7, sticky='w')
    line2 = ttk.Frame(frame)
    line2.grid(row=8, sticky='ew', pady=(6, 18))
    line2.columnconfigure(0, weight=1)
    folder_entry = ttk.Entry(line2, textvariable=folder)
    folder_entry.grid(row=0, column=0, sticky='ew', ipady=6, padx=(0, 10))
    def choose():
        selected = filedialog.askdirectory(initialdir=folder.get())
        if selected:
            folder.set(selected)
    browse = ttk.Button(line2, text='변경', command=choose)
    browse.grid(row=0, column=1)
    buttons = ttk.Frame(frame)
    buttons.grid(row=9, sticky='w', pady=(0, 18))
    start = ttk.Button(buttons, text='다운로드 시작', style='Accent.TButton')
    start.pack(side='left', padx=(0, 10))
    cancel = ttk.Button(buttons, text='취소', state='disabled')
    cancel.pack(side='left', padx=(0, 10))
    def open_folder():
        path = Path(folder.get())
        if path.is_dir():
            os.startfile(str(path))
    ttk.Button(buttons, text='저장 폴더 열기', command=open_folder).pack(side='left')
    ttk.Progressbar(frame, variable=progress, maximum=100).grid(row=10, sticky='ew', ipady=5)
    ttk.Label(frame, textvariable=status, wraplength=710).grid(row=11, sticky='w', pady=(12, 4))
    ttk.Label(frame, textvariable=detail, wraplength=710, foreground='#64748b').grid(row=12, sticky='w')

    def set_busy(busy):
        state['busy'] = busy
        for widget in (check, entry, browse, folder_entry):
            widget.configure(state='disabled' if busy else 'normal')
        combo.configure(state='disabled' if busy else 'readonly')
        start.configure(state='disabled' if busy or not state['checked'] else 'normal')
        cancel.configure(state='normal' if busy else 'disabled')

    def run(action):
        if state['busy']:
            return
        try:
            canonical = normalize_url(url.get())
            if action == 'download':
                if canonical != state['checked']:
                    raise ValueError('링크가 변경되었습니다. 영상 확인을 다시 해주세요.')
                Path(folder.get()).mkdir(parents=True, exist_ok=True)
                if not all((TOOLS / x).is_file() for x in ('ffmpeg.exe', 'node.exe')):
                    raise ValueError('tools 폴더의 FFmpeg 또는 Node 실행 파일이 없습니다.')
        except Exception as exc:
            messagebox.showerror('확인 필요', str(exc))
            return
        state.update(cancelled=False, done=False)
        if action == 'info':
            state['checked'] = None
        progress.set(0)
        status.set('영상 정보를 확인하는 중…' if action == 'info' else '다운로드 준비 중…')
        detail.set('')
        set_busy(True)
        args = [sys.executable] + ([] if getattr(sys, 'frozen', False) else [str(Path(__file__))])
        height = quality.get().split('p')[0] if quality.get() != '최고 화질 자동' else ''
        args += ['--worker', action, canonical, folder.get(), height]
        def read():
            try:
                proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding='utf-8', errors='replace', creationflags=CREATE_FLAGS)
                state['process'] = proc
                if state['cancelled']:
                    stop_process()
                for line in proc.stdout:
                    try:
                        events.put(json.loads(line))
                    except ValueError:
                        pass
                code = proc.wait()
                events.put({'kind': 'exit', 'code': code})
            except Exception as exc:
                events.put({'kind': 'error', 'text': str(exc)})
                events.put({'kind': 'exit', 'code': 1})
        threading.Thread(target=read, daemon=True).start()

    def stop_process():
        proc = state['process']
        if proc and proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], creationflags=CREATE_FLAGS,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cancel_job():
        state['cancelled'] = True
        status.set('취소 중…')
        threading.Thread(target=stop_process, daemon=True).start()

    def poll():
        while not events.empty():
            item = events.get()
            kind = item['kind']
            if kind == 'exit':
                state['process'] = None
                set_busy(False)
                if state['cancelled']:
                    status.set('취소됨 · 미완료 파일은 보관됩니다.')
                elif not state['done'] and item['code'] != 0:
                    if not status.get().startswith('오류:'):
                        status.set('오류: 작업에 실패했습니다. 링크와 인터넷 연결을 확인하세요.')
                continue
            if state['cancelled']:
                continue
            if kind == 'info':
                state['checked'] = normalize_url(url.get())
                seconds = int(item.get('duration') or 0)
                title.set(f"{item['title']} · {seconds // 60}분 {seconds % 60}초")
                combo.configure(values=['최고 화질 자동'] + [f'{h}p 이하' for h in item['heights']])
                quality.set('최고 화질 자동')
                status.set('영상 확인 완료 · 화질을 선택하고 다운로드하세요.')
            elif kind == 'progress':
                progress.set(item['percent'])
                speed = (item.get('speed') or 0) / 1024 / 1024
                eta = item.get('eta')
                status.set(f"현재 트랙 {item['percent']:.1f}% · {speed:.1f} MB/s" + (f' · 약 {eta}초 남음' if eta is not None else ''))
                detail.set(item['filename'])
            elif kind in ('status', 'warning'):
                (status if kind == 'status' else detail).set(item['text'])
            elif kind == 'done':
                state['done'] = True
                progress.set(100)
                status.set('다운로드 완료 · 영상과 소리가 함께 저장되었습니다.')
                detail.set(item['path'])
            elif kind == 'error':
                status.set('오류: ' + item['text'])
        root.after(100, poll)

    def close():
        if state['busy']:
            if not messagebox.askyesno('종료', '진행 중인 작업을 취소하고 종료할까요?'):
                return
            state['cancelled'] = True
            stop_process()
        root.destroy()

    def invalidate(*_):
        if not state['busy']:
            state['checked'] = None
            start.configure(state='disabled')
    url.trace_add('write', invalidate)
    check.configure(command=lambda: run('info'))
    start.configure(command=lambda: run('download'), state='disabled')
    cancel.configure(command=cancel_job)
    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    if '--ui-smoke' in sys.argv:
        root.after(700, root.destroy)
    root.mainloop()


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.stdout.reconfigure(encoding='utf-8')
        try:
            worker(*sys.argv[2:])
        except Exception as exc:
            emit('error', text=str(exc))
            sys.exit(1)
    else:
        main()
