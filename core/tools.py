from datetime import datetime
import xbmc, xbmcplugin, os
import pyqrcode as qr
import urllib.parse

def qrgen(url, path):
    qrc = qr.create(url)
    if os.path.exists(path):
        os.remove(path)
    qrc.png(path, scale=6)
    return path

def n2num(num):
    if isinstance(num, str):
        return num
    if num < 10000:
        return str(num)
    if num < 99999500:
        result = round(num / 10000, 1)
        return str(result) + "万"
    else:
        result = round(num / 100000000, 1)
        return str(result) + "亿"

def ctxt(info, color='red'):
    return f'[COLOR {color}]{info}[/COLOR]'

def dict2url(d):
    return urllib.parse.urlencode(d)

def back():
    xbmc.executebuiltin('Action(Back)')

def get_set(name):
    return xbmcplugin.getSetting(int(sys.argv[1]), name)

def log(msg):
    xbmc.log(f"[bilikodiReborn] (DBG): {msg}", xbmc.LOGINFO)

def err(msg):
    xbmc.log(f"[bilikodiReborn] (ERR): {msg}", xbmc.LOGERROR)

def ts2date(timestamp, ctype=1, custom=False):
    dt = datetime.fromtimestamp(timestamp)
    if custom != False and isinstance(custom, str):
        return dt.strftime(custom)
    if ctype == 2:
        return dt.strftime('%d.%m.%Y')
    elif ctype == 3:
        return dt.strtime('%Y-%m-%d')
    else:
        return dt.strftime('%Y.%m.%d %H:%M:%S')

def chooseR(videos):
    videos = sorted(videos, key=lambda x: (x['id'], x['codecid']), reverse=True)
    # current_id = int(getSetting('video_resolution'))
    # current_codecid = int(getSetting('video_encoding'))
    current_id = 80
    current_codecid = 12

    filtered_videos = []
    max_id = 0
    for video in videos:
        if video['id'] > current_id:
            continue
        if video['id'] == current_id:
            filtered_videos.append(video)
        else:
            if (not filtered_videos) or video['id'] == max_id:
                filtered_videos.append(video)
                max_id = video['id']
            else:
                break
    if not filtered_videos:
        min_id = videos[-1]['id']
        for video in videos:
            if video['id'] == min_id:
                filtered_videos.append(video)


    final_videos = []
    max_codecid = 0
    for video in filtered_videos:
        if video['codecid'] > current_codecid:
            continue
        if video['codecid'] == current_codecid:
            final_videos.append(video)
        else:
            if (not final_videos) or video['codecid'] == max_codecid:
                final_videos.append(video)
                max_codecid = video['codecid']
            else:
                break
    if not final_videos:
        min_codecid = videos[-1]['codecid']
        for video in videos:
            if video['codecid'] == min_codecid:
                final_videos.append(video)

    return final_videos

def genmpd(dash):
    videos = chooseR(dash["video"])
    audios = dash['audio']

    list = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static" mediaPresentationDuration="PT', str(dash['duration']), 'S" minBufferTime="PT', str(dash['minBufferTime']), 'S">\n',
        '\t<Period>\n'
    ]

    # video
    list.append('\t\t<AdaptationSet mimeType="video/mp4" startWithSAP="1" scanType="progressive" segmentAlignment="true">\n')
    for video in videos:
        list.extend([
            '\t\t\t<Representation bandwidth="', str(video['bandwidth']), '" codecs="', video['codecs'], '" frameRate="', video['frameRate'], '" height="', str(video['height']), '" width="', str(video['width']), '" id="', str(video['id']), '">\n',
            '\t\t\t\t<BaseURL>', video['baseUrl'].replace('&', '&amp;'), '</BaseURL>\n',
            '\t\t\t\t<SegmentBase indexRange="', video['SegmentBase']['indexRange'], '">\n',
            '\t\t\t\t\t<Initialization range="' + video['SegmentBase']['Initialization'] + '"></Initialization>\n',
            '\t\t\t\t</SegmentBase>\n',
            '\t\t\t</Representation>\n'
        ])
    list.append('\t\t</AdaptationSet>\n')

    # audio
    list.append('\t\t<AdaptationSet mimeType="audio/mp4" startWithSAP="1" segmentAlignment="true" lang="und">\n')
    for audio in audios:
        list.extend([
            '\t\t\t<Representation audioSamplingRate="44100" bandwidth="', str(audio['bandwidth']), '" codecs="', audio['codecs'], '" id="', str(audio['id']), '">\n',
            '\t\t\t\t<BaseURL>', audio['baseUrl'].replace('&', '&amp;'), '</BaseURL>\n',
            '\t\t\t\t<SegmentBase indexRange="', audio['SegmentBase']['indexRange'], '">\n',
            '\t\t\t\t\t<Initialization range="' + audio['SegmentBase']['Initialization'] + '"></Initialization>\n',
            '\t\t\t\t</SegmentBase>\n',
            '\t\t\t</Representation>\n'
        ])
    list.append('\t\t</AdaptationSet>\n')

    list.append('\t</Period>\n</MPD>\n')

    return ''.join(list)