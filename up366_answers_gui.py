#!/usr/bin/env python3
"""Tkinter tool: pick the up366 data dir, pick up366.exe once, save key config, parse homework answers."""

import datetime
import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))

from extract_answers import build_answer_text, homework_dirs  # noqa: E402
from u3enc_tool import extract_key  # noqa: E402

DEFAULT_DATA_DIR = Path(r'D:\Up366StudentFiles')
DEFAULT_EXE = WORKSPACE / 'up366.exe'
CONFIG_PATH = WORKSPACE / 'config' / 'gui_config.json'
ANSWERS_DIR = WORKSPACE / 'answers'


class AnswersGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('up366 作业答案解析')
        self.root.geometry('880x520')
        self.root.minsize(720, 420)

        self.config = self.load_config()
        self.data_dir = Path(self.config.get('data_dir') or DEFAULT_DATA_DIR)
        self.exe_path = Path(self.config.get('exe_path') or DEFAULT_EXE)
        self._hw_by_iid = {}

        self.status_var = tk.StringVar(value='正在初始化...')
        self._build_ui()
        self.root.after(100, self._initial_setup)

    def _build_ui(self):
        pad = {'padx': 8, 'pady': 5}
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill='both', expand=True)

        row1 = ttk.Frame(frame)
        row1.pack(fill='x', **pad)
        ttk.Label(row1, text='Up366StudentFiles:').pack(side='left')
        self.data_var = tk.StringVar(value=str(self.data_dir))
        self.data_entry = ttk.Entry(row1, textvariable=self.data_var, state='readonly')
        self.data_entry.pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(row1, text='选择目录', command=self.choose_data_dir).pack(side='right')

        row2 = ttk.Frame(frame)
        row2.pack(fill='x', **pad)
        ttk.Label(row2, text='up366.exe:').pack(side='left')
        self.exe_var = tk.StringVar(value=str(self.exe_path))
        self.exe_entry = ttk.Entry(row2, textvariable=self.exe_var, state='readonly')
        self.exe_entry.pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(row2, text='选择 exe', command=self.prompt_exe).pack(side='right')

        tool_row = ttk.Frame(frame)
        tool_row.pack(fill='x', **pad)
        ttk.Button(tool_row, text='刷新列表', command=self.load_homeworks).pack(side='left')
        ttk.Button(tool_row, text='解析选中作业', command=self.parse_selected).pack(side='right')

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill='both', expand=True, **pad)
        columns = ('uuid', 'book', 'mtime')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        self.tree.heading('uuid', text='作业UUID')
        self.tree.heading('book', text='书本UUID')
        self.tree.heading('mtime', text='修改时间')
        self.tree.column('uuid', width=270)
        self.tree.column('book', width=270)
        self.tree.column('mtime', width=150, anchor='center')
        yscroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        yscroll.pack(side='right', fill='y')

        status = ttk.Label(frame, textvariable=self.status_var, anchor='w')
        status.pack(fill='x', side='bottom', padx=8, pady=(0, 4))

    def _initial_setup(self):
        self._update_path_entries()
        if not self._valid_key(self.config.get('key_hex')):
            self.status_var.set('首次使用，请定位 up366.exe')
            self.ensure_key()
        else:
            self.status_var.set('已从配置加载密钥')
        self.load_homeworks()

    @staticmethod
    def load_config():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {}

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    @staticmethod
    def _valid_key(key_hex):
        if not key_hex:
            return False
        try:
            return len(bytes.fromhex(key_hex)) == 16
        except ValueError:
            return False

    def _update_path_entries(self):
        self.data_var.set(str(self.data_dir))
        self.exe_var.set(str(self.exe_path))

    def choose_data_dir(self):
        initial = str(self.data_dir) if self.data_dir.is_dir() else 'D:/'
        path = filedialog.askdirectory(title='选择 Up366StudentFiles 目录', initialdir=initial)
        if not path:
            return
        self.data_dir = Path(path)
        self.config['data_dir'] = str(self.data_dir)
        self.save_config()
        self._update_path_entries()
        self.status_var.set(f'已保存配置，加载目录: {self.data_dir}')
        self.load_homeworks()

    def prompt_exe(self):
        initial_dir = str(self.exe_path.parent) if self.exe_path.is_file() else 'D:/'
        path = filedialog.askopenfilename(
            title='定位 up366.exe',
            initialdir=initial_dir,
            filetypes=[('Executable', '*.exe'), ('All files', '*.*')],
        )
        if not path:
            return None
        self.exe_path = Path(path)
        self.config['exe_path'] = str(self.exe_path)
        self._update_path_entries()
        return self.exe_path

    def ensure_key(self):
        exe = self.exe_path
        if not exe.is_file():
            exe = self.prompt_exe()
            if exe is None:
                self.status_var.set('未定位 up366.exe，无法解析')
                return False
        try:
            key_b64, key, _ = extract_key(exe)
            self.config['exe_path'] = str(exe)
            self.config['key_hex'] = key.hex()
            self.config['key_base64'] = key_b64
            self.save_config()
            self._update_path_entries()
            self.status_var.set(f'密钥已提取并保存: {key.hex()}')
            return True
        except Exception as exc:
            messagebox.showerror('提取密钥失败', str(exc))
            self.status_var.set('密钥提取失败')
            return False

    def load_homeworks(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._hw_by_iid.clear()

        if not self.data_dir.is_dir():
            messagebox.showerror('目录不存在', f'{self.data_dir} 不存在，请重新选择')
            self.status_var.set('目录不存在')
            return

        try:
            rows = homework_dirs(self.data_dir)
        except Exception as exc:
            messagebox.showerror('加载失败', str(exc))
            return

        if not rows:
            self.status_var.set(f'{self.data_dir} 下未找到作业目录')
            return

        for mtime, hw_uuid, book_uuid, hw_dir in rows:
            iid = hw_uuid
            self._hw_by_iid[iid] = hw_dir
            self.tree.insert(
                '',
                'end',
                iid=iid,
                values=(
                    hw_uuid,
                    book_uuid,
                    datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                ),
            )

        first = self.tree.get_children()[0]
        self.tree.selection_set(first)
        self.tree.focus(first)
        self.status_var.set(f'共 {len(rows)} 个作业，默认选中最新')

    def parse_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning('未选择作业', '请先在列表中选择一个作业')
            return
        hw_dir = self._hw_by_iid.get(selection[0])
        if hw_dir is None:
            messagebox.showerror('解析失败', '选中的作业路径无效，请刷新列表')
            return

        key_hex = self.config.get('key_hex')
        if not self._valid_key(key_hex):
            if not self.ensure_key():
                return
            key_hex = self.config.get('key_hex')
        key = bytes.fromhex(key_hex)

        self.status_var.set(f'正在解析 {hw_dir.name} ...')
        self.root.update_idletasks()
        try:
            text, items = build_answer_text(self.data_dir, hw_dir, key)
            ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
            output = ANSWERS_DIR / f'{hw_dir.name}.txt'
            output.write_text(text, encoding='utf-8-sig')
            self.status_var.set(f'已生成 {len(items)} 题 -> {output}')
            os.startfile(output)
        except Exception as exc:
            messagebox.showerror('解析失败', str(exc))
            self.status_var.set('解析失败')


def main():
    root = tk.Tk()
    AnswersGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
