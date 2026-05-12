from datetime import datetime
import xbmc, xbmcplugin, os
import pyqrcode as qr

def qrgen(url, path):
    qrc = qr.create(url)
    if os.path.exists(path):
        os.remove(path)
    qrc.png(path, scale=6)
    return path

def back():
    xbmc.executebuiltin('Action(Back)')

def get_set(name):
    return xbmcplugin.getSetting(int(sys.argv[1]), name)

def log(msg):
    xbmc.log(f"[bilikodiReborn] (DBG): {msg}", xbmc.LOGINFO)

def err(msg):
    xbmc.log(f"[bilikodiReborn] (ERR): {msg}", xbmc.LOGERROR)

def ts2date(timestamp):
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y.%m.%d %H:%M:%S')