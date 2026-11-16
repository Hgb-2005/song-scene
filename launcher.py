"""Windowed desktop entry. Python is included in the Windows installer."""
from pathlib import Path
import argparse
import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,messagebox
import webbrowser

from desktop.runtime import VERSION,resource_root,data_directory,InstanceLock
from desktop.engine import usable_tools,provision,engine_directory
from server.http import Workspace,make_server


class Desktop:
    def __init__(self,window,directory,lock,auto_open=True):
        self.window=window;self.directory=directory;self.lock=lock;self.auto_open=auto_open
        self.events=queue.Queue();self.cancel=threading.Event();self.server=None;self.workspace=None;self.worker=None;self.stopping=False
        window.title('一歌一景 · 创作工作台 V8');window.geometry('540x390');window.minsize(500,390);window.configure(bg='#f7f6ef')
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',font=('Microsoft YaHei UI',10),padding=9)
        frame=tk.Frame(window,bg='#f7f6ef',padx=32,pady=27);frame.pack(fill='both',expand=True)
        tk.Label(frame,text='一歌一景',font=('Microsoft YaHei UI',26,'bold'),fg='#234b39',bg='#f7f6ef').pack(anchor='w')
        tk.Label(frame,text='让一首歌，成为一段看得见的心情。',font=('Microsoft YaHei UI',10),fg='#68776c',bg='#f7f6ef').pack(anchor='w',pady=(4,20))
        self.status=tk.StringVar(value='正在打开本机工作台……')
        tk.Label(frame,textvariable=self.status,font=('Microsoft YaHei UI',10),fg='#234b39',bg='#f7f6ef',wraplength=465,justify='left').pack(anchor='w')
        self.progress=ttk.Progressbar(frame,maximum=100);self.progress.pack(fill='x',pady=12)
        actions=tk.Frame(frame,bg='#f7f6ef');actions.pack(fill='x',pady=8)
        self.open_button=ttk.Button(actions,text='打开创作工作台',command=self.open,state='disabled');self.open_button.pack(side='left')
        ttk.Button(actions,text='打开数据文件夹',command=lambda:os.startfile(self.directory)).pack(side='left',padx=10)
        self.retry_button=ttk.Button(frame,text='重试准备视频引擎',command=self.start)
        tk.Label(frame,text='作品保存在电脑里。升级、卸载程序都会保留数据。\n关闭此窗口会停止本机服务；浏览器页面可重新打开。',font=('Microsoft YaHei UI',9),fg='#68776c',bg='#f7f6ef',justify='left').pack(anchor='w',pady=10)
        tk.Label(frame,text=f'V{VERSION}  ·  本机制作，无需账号',font=('Microsoft YaHei UI',8),fg='#68776c',bg='#f7f6ef').pack(anchor='w')
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(100,self.poll);self.start()

    def start(self):
        self.retry_button.pack_forget();self.cancel.clear()
        def prepare():
            try:
                if not usable_tools():
                    self.events.put(('progress',('首次使用需要联网准备视频引擎（约 109 MB），以后可离线制作。',0)))
                    provision(lambda text,value:self.events.put(('progress',(text,value))),self.cancel)
                    if not usable_tools():raise RuntimeError('视频引擎无法运行，请检查系统是否为 Windows 10/11 64 位。')
                if self.cancel.is_set():return
                self.workspace=Workspace(resource_root(),self.directory)
                self.server=make_server(self.workspace,0)
                self.lock.publish(self.server.server_port)
                threading.Thread(target=self.server.serve_forever,daemon=True).start()
                self.events.put(('ready',None))
            except Exception as error:
                logging.exception('Desktop startup failed')
                self.events.put(('error',str(error)))
        self.worker=threading.Thread(target=prepare,daemon=True);self.worker.start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value[0]);self.progress['value']=value[1]
                elif kind=='ready':
                    self.status.set('工作台已就绪。可以在浏览器里创作了。');self.progress['value']=100;self.open_button['state']='normal'
                    if self.auto_open:self.open()
                elif kind=='error':
                    self.status.set('暂时没能打开：'+value);self.retry_button.pack(anchor='w',before=self.open_button.master);self.progress['value']=0
                elif kind=='stopped':self.lock.close();self.window.destroy();return
        except queue.Empty:pass
        self.window.after(100,self.poll)

    def open(self):
        if self.server:webbrowser.open(f'http://127.0.0.1:{self.server.server_port}/index.html')

    def close(self):
        if self.stopping:return
        active=self.workspace and any(j.get('status') in ['queued','running'] for j in self.workspace.store.list('job'))
        if active and not messagebox.askyesno('合成还在进行','现在退出会取消本次合成，方案和原素材会保留。确定退出吗？',parent=self.window):return
        self.stopping=True;self.cancel.set();self.status.set('正在保存状态并退出……');self.open_button['state']='disabled'
        def stop():
            self.worker.join()
            if self.server:self.server.shutdown();self.server.server_close()
            if self.workspace:self.workspace.close()
            self.events.put(('stopped',None))
        self.worker_stop=threading.Thread(target=stop,daemon=True);self.worker_stop.start();self.window.after(100,self.poll)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',type=Path,default=data_directory());parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args();directory=args.data_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=directory/'desktop.log',level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')
    lock=InstanceLock(directory)
    if not lock.acquire():
        url=lock.existing_url()
        if url and not args.no_open:webbrowser.open(url)
        elif not url:
            window=tk.Tk();window.withdraw();messagebox.showinfo('一歌一景','工作台正在启动或退出，请稍等片刻。');window.destroy()
        return
    window=tk.Tk()
    try:Desktop(window,directory,lock,not args.no_open);window.mainloop()
    finally:lock.close()


if __name__=='__main__':main()
