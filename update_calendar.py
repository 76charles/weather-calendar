import os
import requests
import pytz
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# --- [설정] ---
NX, NY = 60, 127
LOCATION_NAME = "봉화산로 193"
REG_ID_TEMP = '11B10101'
REG_ID_LAND = '11B00000'
API_KEY = os.environ.get('KMA_API_KEY')

def get_weather_info(sky, pty):
    sky, pty = str(sky), str(pty)
    if pty == '0':
        if sky == '1': return "☀️", "맑음"
        if sky == '3': return "⛅", "구름많음"
        if sky == '4': return "☁️", "흐림"
    else:
        if pty in ['1', '4']: return "🌧️", "비/소나기"
        if pty == '2': return "🌨️", "비/눈"
        if pty == '3': return "❄️", "눈"
    return "🌡️", "정보없음"

def get_mid_emoji(wf):
    if '비' in wf or '소나기' in wf: return "🌧️"
    if '눈' in wf: return "🌨️"
    if '구름많음' in wf: return "⛅"
    if '흐림' in wf: return "☁️"
    return "☀️"

def fetch_api(url):
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200: return res.json()
    except: return None
    return None

def main():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    cal = Calendar()
    cal.add('X-WR-CALNAME', '기상청 날씨')
    cal.add('X-WR-TIMEZONE', 'Asia/Seoul')

    # --- [A. 단기 예보 수집] (매회 실행) ---
    base_date = now.strftime('%Y%m%d')
    # 기상청 업데이트 시간에 맞춘 base_time 설정
    base_h = max([h for h in [2, 5, 8, 11, 14, 17, 20, 23] if h <= now.hour], default=2)
    base_time = f"{base_h:02d}00"
    
    url_short = f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?dataType=JSON&base_date={base_date}&base_time={base_time}&nx={NX}&ny={NY}&numOfRows=1000&authKey={API_KEY}"
    
    forecast_map = {}
    short_res = fetch_api(url_short)
    if short_res and 'response' in short_res and 'body' in short_res['response']:
        items = short_res['response']['body']['items']['item']
        for it in items:
            d, t, cat, val = it['fcstDate'], it['fcstTime'], it['category'], it['fcstValue']
            if d not in forecast_map: forecast_map[d] = {}
            if t not in forecast_map[d]: forecast_map[d][t] = {}
            forecast_map[d][t][cat] = val

    # --- [B. 중기 예보 수집] (특정 시간에만 실행) ---
    # 기상청 중기 업데이트(06, 18시) 직후인 05:15(KST), 17:15(KST) 회차에서 호출
    # (액션 스케줄 상 05:15, 17:15에 실행됨)
    mid_map = {}
    if now.hour in [5, 17]:
        print(f"📢 중기 예보 업데이트 시간({now.hour}시) - API 호출을 시작합니다.")
        tm_fc = now.strftime('%Y%m%d') + ("0600" if now.hour < 12 else "1800")
        url_mid_temp = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa?dataType=JSON&regId={REG_ID_TEMP}&tmFc={tm_fc}&authKey={API_KEY}"
        url_mid_land = f"https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst?dataType=JSON&regId={REG_ID_LAND}&tmFc={tm_fc}&authKey={API_KEY}"
        
        mid_temp_res = fetch_api(url_mid_temp)
        mid_land_res = fetch_api(url_mid_land)
        
        if mid_temp_res and mid_land_res:
            try:
                t_item = mid_temp_res['response']['body']['items']['item'][0]
                l_item = mid_land_res['response']['body']['items']['item'][0]
                for i in range(4, 11):
                    d_str = (now + timedelta(days=i)).strftime('%Y%m%d')
                    if i <= 7:
                        mid_map[d_str] = {
                            'min': t_item.get(f'taMin{i}'), 'max': t_item.get(f'taMax{i}'),
                            'wf_am': l_item.get(f'wf{i}Am'), 'wf_pm': l_item.get(f'wf{i}Pm'),
                            'rn_am': l_item.get(f'rnSt{i}Am'), 'rn_pm': l_item.get(f'rnSt{i}Pm')
                        }
                    else:
                        mid_map[d_str] = {
                            'min': t_item.get(f'taMin{i}'), 'max': t_item.get(f'taMax{i}'),
                            'wf': l_item.get(f'wf{i}'), 'rn': l_item.get(f'rnSt{i}')
                        }
            except Exception as e: print(f"중기 데이터 파싱 에러: {e}")
    else:
        print(f"ℹ️ {now.hour}시는 중기 업데이트 시간이 아니므로 건너뜁니다.")

    # --- [C. ics 생성 로직] --- (이전과 동일하게 단기 3일, 중기 4~10일 처리)
    for i in range(11):
        target_dt = now + timedelta(days=i)
        d_str = target_dt.strftime('%Y%m%d')
        event = Event()
        
        if i <= 3 and d_str in forecast_map:
            d_data = forecast_map[d_str]
            times = sorted(d_data.keys())
            tmps = [float(d_data[t]['TMP']) for t in times if 'TMP' in d_data[t]]
            if tmps:
                t_min, t_max = int(min(tmps)), int(max(tmps))
                mid_t = "1200" if "1200" in d_data else times[len(times)//2]
                rep_em, _ = get_weather_info(d_data[mid_t].get('SKY'), d_data[mid_t].get('PTY'))
                event.add('summary', f"{rep_em} {t_min}°C / {t_max}°C")
                desc = [f"📍 {LOCATION_NAME}\n"]
                for t in times:
                    it = d_data[t]
                    em, status = get_weather_info(it.get('SKY'), it.get('PTY'))
                    pop_str = f"☔{it.get('POP')}% " if it.get('PTY') != '0' else ""
                    line = f"[{int(t[:2])}시] {em} {it.get('TMP')}°C {status} ({pop_str}💧{it.get('REH')}% 💨{it.get('WSD')}m/s)"
                    desc.append(line)
                desc.append(f"\n최종 갱신: {now.strftime('%Y-%m-%d %H:%M:%S')} KST")
                event.add('description', "\n".join(desc))
        elif d_str in mid_map:
            m = mid_map[d_str]
            rep_wf = m.get('wf_pm') or m.get('wf')
            event.add('summary', f"{get_mid_emoji(rep_wf)} {m['min']}°C / {m['max']}°C")
            desc = [f"📍 {LOCATION_NAME}\n"]
            if 'wf_am' in m:
                desc.append(f"[오전] {get_mid_emoji(m['wf_am'])} {m['wf_am']} (☔{m['rn_am']}%)")
                desc.append(f"[오후] {get_mid_emoji(m['wf_pm'])} {m['wf_pm']} (☔{m['rn_pm']}%)")
            else:
                desc.append(f"[종일] {get_mid_emoji(m['wf'])} {m['wf']} (☔{m['rn']}%)")
            event.add('description', "\n".join(desc))

        event.add('dtstart', target_dt.date())
        event.add('dtend', (target_dt + timedelta(days=1)).date())
        event.add('uid', f"{d_str}@kma_weather")
        cal.add_component(event)

    with open('weather.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    main()
