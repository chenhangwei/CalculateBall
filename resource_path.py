import sys
import os

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    # 数据库文件列表 - 这些文件应该从exe所在目录读取，而不是从临时目录
    db_files = ['wind.db', 'Cable.db', 'Film.db', 'Tube.db']
    
    # 检查是否是数据库文件
    if any(db in relative_path for db in db_files):
        # 数据库文件从exe所在目录读取
        if getattr(sys, 'frozen', False):
            # 如果是打包后的exe，从exe所在目录读取
            base_path = os.path.dirname(sys.executable)
        else:
            # 开发环境，从当前目录读取
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    # 其他资源文件
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
