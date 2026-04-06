import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [1. 설정] ---
NX = int(os.environ.get('KMA_NX', 60))
NY = int(os.environ.get('KMA_NY', 127))
LOCATION_NAME = os.environ.get('LOCATION_NAME', '내 위치')
REG_ID_TEMP = os.environ.get('REG_ID_TEMP', '11B10101')
REG_ID_LAND = os.environ.get('REG_ID_LAND', '11B00000')
API_KEY = os.environ['KMA_API_KEY']

def get_weather_info(sky, pty):
    """
    기상청 단기예보 강수형태(PTY) 공식 코드 반영
    0: 없음, 1: 비, 2: 비/눈, 3: 눈, 4: 소나기, 5: 빗방울, 6: 빗방울눈날림, 7: 눈날림
    """
    sky, pty = str(sky), str(pty)
    
    # 1. 강수 형태가 있는 경우 (PTY != '0')
    if pty == '1': return "🌧️", "비"
    if pty == '2': return "🌨️", "비/눈(진눈깨비)"
    if pty == '3': return "❄️", "눈"
    if pty == '4': return "☔", "소나기"
    if pty == '5': return "💧", "빗방울"
    if pty == '6': return "🌨️", "빗방울/눈날림"
    if pty == '7': return "❄️", "눈날림"

    # 2. 강수 형태가 없는 경우 (PTY == '0'), 하늘상태(SKY) 기준
    if sky == '1': return "☀️", "맑음"
    if sky == '3': return "⛅", "구름많음"
    if sky == '4': return "☁️", "흐림"
    
    return "🌡️", "정보없음"

def get_mid_emoji(wf):
    """중기 예보 기상 상태(텍스트 기반) 판별"""
    if not wf: return "🌡️"
    wf = wf.replace(" ", "")
    if '소나기' in wf: return "☔"
    if '비' in wf: return "🌧️"
    if '눈' in wf or '진눈깨비' in wf: return "🌨️"
    if '구름많음' in wf: return "⛅"
    if '흐림' in wf: return "☁️"
    if '맑음' in wf: return "☀️"
    return "☀️"

def fetch_api(url):
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get('response', {}).get('header', {}).get('resultCode') == '00':
                return data
        return None
    except:
        return None

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    update_ts = now.strftime('%Y-%m-%d %H:%M:%S')
    
    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # --- [2. 단기 예보 (오늘 ~ +3일)] ---
    base_date = now.strftime('%Y%m%d')
    base_h = max([h for h in [2, 5, 8, 11, 14, 17, 20, 23] if h <= now.hour], default=2)
    base_time = f"{base_h:02d}00"
    
    url_short = f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?dataType=JSON&base_date={base_date}&base_time={base_time}&nx={NX}&ny={NY}&numOfRows=1000&authKey={API_KEY}"
    
    forecast_map = {}
    short_res = fetch_api(url_short)
    processed_dates = set()

    if short_res and 'body' in short_res['response']:
        items = short_res['response']['body']['items']['item']
        for it in items:
            d, t, cat, val = it['fcstDate'], it['fcstTime'], it['category'], it['fcstValue']
            if d not in forecast_map: forecast_map[d] = {}
            if t not in forecast_map[d]: forecast_map[d][t] = {}
            forecast_map[d][t][cat] = val

    cache = {'TMP': '15', 'SKY': '1', 'PTY': '0', 'REH': '50', 'WSD': '1.0', 'POP': '0'}
    short_term_limit = (now + timedelta(days=3)).strftime('%Y%m%d')

    for d_str in sorted(forecast_map.keys()):
        if d_str > short_term_limit: continue

        day_data = forecast_map[d_str]
        tmps = [float(day_data[t]['TMP']) for t in day_data if 'TMP' in day_data[t]]
        if not tmps: continue
        
        t_min, t_max = int(min(tmps)), int(max(tmps))
        rep_t = '1200' if '1200' in day_data else sorted(day_data.keys())[0]
        rep_emoji, _ = get_weather_info(day_data[rep_t].get('SKY', cache['SKY']), day_data[rep_t].get('PTY', cache['PTY']))
        
        desc = []
        has_future_data = False
        for h in range(24):
            t_str = f"{h:02d}00"
            event_time = seoul_tz.localize(datetime.strptime(f"{d_str}{t_str}", '%Y%m%d%H%M'))
            
            if t_str in day_data:
                for cat in cache.keys():
                    if cat in day_data[t_str]: cache[cat] = day_data[t_str][cat]
            
            if event_time >= now:
                emoji, wf_str = get_weather_info(cache['SKY'], cache['PTY'])
                # 강수확률(POP)은 비가 안 와도 표시, 비가 오면 아이콘 변경
                rain_icon = "☔" if cache['PTY'] != '0' else "💧"
                desc.append(f"[{t_str[:2]}시] {emoji} {wf_str} {cache['TMP']}°C ({rain_icon}{cache['POP']}% 습도{cache['REH']}% 풍속{cache['WSD']}m/s)")
                has_future_data = True
        
        if not has_future_data: continue

        event = Event()
        event.add('summary', f"{rep_emoji} {t_min}°C/{t_max}°C")
        event.add('location', LOCATION_NAME)
        desc.append(f"\n최종 업데이트: {update_ts} (KST)")
        event.add('description', "\n".join(desc))
        
        event_date = datetime.strptime(d_str, '%Y%m%d').date()
        event.add('dtstart', event_date)
        event.add('dtend', event_date + timedelta(days=1))
        event.add('uid', f"{d_str}@short_summary")
        cal.add_component(event)
        processed_dates.add(d_str)

    # --- [3. 중기 예보 (14:00 업데이트 이슈 해결 로직)] ---
    # 오후 6시 30분 전까지는 안전하게 오전 6시 데이터를 참조
    if now.hour < 6:
        tm_fc = (now - timedelta(days=1)).strftime('%Y%m%d') + "1800"
    elif now.hour < 18:
        tm_fc = now.strftime('%Y%m%d') + "0600"
    else:
        tm_fc = now.strftime('%Y%m%d') + "1800"

    url_mid_temp = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc}&authKey={API_KEY}"
    url_mid_land = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc}&authKey={API_KEY}"
    
    t_res, l_res = fetch_api(url_mid_temp), fetch_api(url_mid_land)
    
    # 만약 18:00 데이터가 아직 생성 전이라 실패하면 06:00 데이터로 백업 호출
    if not (t_res and l_res) and tm_fc.endswith("1800"):
        tm_fc = now.strftime('%Y%m%d') + "0600"
        url_mid_temp = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc}&authKey={API_KEY}"
        url_mid_land = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc}&authKey={API_KEY}"
        t_res, l_res = fetch_api(url_mid_temp), fetch_api(url_mid_land)

    if t_res and l_res:
        try:
            t_items = t_res['response']['body']['items']['item'][0]
            l_items = l_res['response']['body']['items']['item'][0]
            for i in range(3, 11):
                d_target_dt = now + timedelta(days=i)
                d_target_str = d_target_dt.strftime('%Y%m%d')
                if d_target_str in processed_dates: continue
                
                t_min, t_max = t_items.get(f'taMin{i}'), t_items.get(f'taMax{i}')
                if t_min is None or t_max is None: continue
                
                wf_rep = l_items.get(f'wf{i}Pm') if i <= 7 else l_items.get(f'wf{i}')
                if wf_rep is None: continue

                event = Event()
                mid_desc = []
                if i <= 7:
                    wf_am, wf_pm = l_items.get(f'wf{i}Am'), l_items.get(f'wf{i}Pm')
                    rn_am, rn_pm = l_items.get(f'rnSt{i}Am'), l_items.get(f'rnSt{i}Pm')
                    mid_desc.append(f"[오전] {get_mid_emoji(wf_am)} {wf_am} (☔{rn_am}%)")
                    mid_desc.append(f"[오후] {get_mid_emoji(wf_pm)} {wf_pm} (☔{rn_pm}%)")
                else:
                    wf_rep_val, rn_st = l_items.get(f'wf{i}'), l_items.get(f'rnSt{i}')
                    mid_desc.append(f"[종일] {get_mid_emoji(wf_rep_val)} {wf_rep_val} (☔{rn_st}%)")

                event.add('summary', f"{get_mid_emoji(wf_rep)} {wf_rep} {t_min}/{t_max}°C")
                event.add('location', LOCATION_NAME)
                mid_desc.append(f"\n최종 업데이트: {update_ts} (KST)")
                event.add('description', "\n".join(mid_desc))
                
                event_date = d_target_dt.date()
                event.add('dtstart', event_date)
                event.add('dtend', event_date + timedelta(days=1))
                event.add('uid', f"{d_target_str}@mid")
                cal.add_component(event)
        except:
            pass

    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    main()
