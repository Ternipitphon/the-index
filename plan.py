"""
AgriFuture AI — Combined Flask Backend (สำหรับ deploy บน Render)
==================================================================
รวม 3 ฟีเจอร์เข้าไฟล์เดียว เพื่อให้ Render รันได้ด้วย entrypoint เดียว:

  1. /api/analyze          — วิเคราะห์การปลูกพืช (Gemini)      [เดิมจาก app.py]
  2. /api/locations        — รายชื่อจังหวัดที่รองรับ            [เดิมจาก Phaya.py]
     /api/weather/<province> — พยากรณ์อากาศ (Open-Meteo)        [เดิมจาก Phaya.py]
  3. /chat                 — แชท AI (Gemini แทน Ollama เดิม)   [ปรับจาก Chat.py]

และเสิร์ฟไฟล์หน้าเว็บทั้งหมด (html/css/js/img/video) จาก root ของ repo เอง
เพราะไฟล์ .html เดิมเรียก css/js ด้วย relative path อยู่แล้ว

ต้องตั้งค่า Environment Variable บน Render:
  GEMINI_API_KEY = <api key ของคุณ>
"""

import os
import json
import time
from datetime import datetime

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ── เสิร์ฟไฟล์ static ทั้งหมดจาก root ของ repo (เดียวกับที่ app.py วางไว้) ──
app = Flask(__name__, static_folder='.', static_url_path='')

# อนุญาต CORS สำหรับทุกโดเมนและรองรับ Content-Type: application/json ข้ามโดเมนได้ 100%
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/chat": {"origins": "*"}})

# กำหนด API Key ของ Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


# ══════════════════════════════════════════════════════════════
# หน้าเว็บ (static pages)
# ══════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return app.send_static_file('form.html')


@app.route('/<path:filename>')
def serve_page(filename):
    return app.send_static_file(filename)


# ══════════════════════════════════════════════════════════════
# 1) วิเคราะห์การปลูกพืช — /api/analyze  (เดิมจาก app.py)
# ══════════════════════════════════════════════════════════════
def generate_content_with_retry(model, prompt, retries=5, backoff_in_seconds=2):
    for i in range(retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(backoff_in_seconds * (2 ** i))
                continue
            raise e


@app.route('/api/analyze', methods=['POST'])
def analyze_crop():
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "[AgriFuture-Backend] ไม่พบข้อมูลที่ส่งมาจากหน้าบ้าน (Body ว่างเปล่า)"}), 400

        province        = data.get('province', '')
        district        = data.get('district', '')
        budget          = data.get('budget', '')
        area            = data.get('area', '')
        water_source    = data.get('water_source', '')
        planting_month  = data.get('planting_month', '')
        interested_crop = data.get('interested_crop', '')

        if not interested_crop:
            return jsonify({"success": False, "error": "[AgriFuture-Backend] ไม่พบข้อมูลชื่อพืชที่สนใจส่งมาวิเคราะห์"}), 400

        if not os.environ.get("GEMINI_API_KEY"):
            return jsonify({"success": False, "error": "[AgriFuture-Backend] ไม่พบ GEMINI_API_KEY กรุณาตั้งค่าใน Environment Variables"}), 500

        prompt = f"""
คุณคือ AI ผู้เชี่ยวชาญด้านการเกษตรอัจฉริยะ (AgriFuture AI)
จงวิเคราะห์ความเหมาะสมในการปลูกพืชตามข้อมูลของผู้ใช้ต่อไปนี้ด้วยความรอบคอบสูงสุด:
- พืชที่สนใจปลูก: {interested_crop}
- พื้นที่แปลงปลูก: อำเภอ {district} จังหวัด {province} (ขนาดพื้นที่: {area})
- งบประมาณเริ่มต้นที่ตั้งไว้: {budget} บาท
- แหล่งน้ำที่สามารถเข้าถึงได้: {water_source}
- ช่วงเวลาที่จะเริ่มทำการปลูก: เดือน {planting_month}

จงประเมินความเป็นไปได้เชิงวิชาการเกษตรและการคาดการณ์สภาวะตลาด และตอบกลับมาเป็นรูปแบบโครงสร้าง JSON ภาษาไทยเท่านั้น ห้ามมีคำอธิบายอื่นนอกเหนือจาก JSON โครงสร้างต้องตรงตามรูปแบบตัวอย่างนี้เป๊ะๆ:
{{
  "selected_crop": {{
    "name": "{interested_crop}",
    "success_chance": "สูง หรือ ปานกลาง หรือ ต่ำ",
    "success_percent": 85,
    "estimated_income": "80,000 - 120,000",
    "roi_months": "6 - 8",
    "pros": ["ระบุข้อดีเกษตรกรรม/การตลาดของพืชนี้ตัวเลือกที่ 1", "ระบุข้อดีตัวเลือกที่ 2"],
    "cons": ["ระบุปัจจัยเสี่ยง/ปัญหาของพืชนี้ตัวเลือกที่ 1", "ระบุปัจจัยเสี่ยงตัวเลือกที่ 2"],
    "tips": ["เคล็ดลับการปลูกให้ได้ผลผลิตดีสำหรับมือใหม่ 1", "เคล็ดลับที่ 2"]
  }},
  "alternative_crops": [
    {{
      "name": "ชื่อพืชทางเลือกแนะนำชนิดที่ 1",
      "success_percent": 90,
      "success_chance": "สูง",
      "difficulty": "ง่าย",
      "market_trend": "เติบโตสูง",
      "estimated_income": "100,000",
      "roi_months": "5",
      "reason": "อธิบายเหตุผลว่าทำไมพืชชนิดนี้ถึงเหมาะสมกับทรัพยากรของเขาในพื้นที่นี้"
    }}
  ],
  "monthly_crops": {{
    "มกราคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "กุมภาพันธ์": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "มีนาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "เมษายน": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "พฤษภาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "มิถุนายน": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "กรกฎาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "สิงหาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "กันยายน": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "ตุลาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "พฤศจิกายน": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }},
    "ธันวาคม": {{ "crop": "พืชราคาดีที่ควรปลูกเดือนนี้", "note": "เหตุผลประกอบทางเศรษฐศาสตร์" }}
  }},
  "general_advice": "บทสรุปเชิงลึกและคำแนะนำภาพรวมจากระบบ AI เพื่อความมั่นใจของเกษตรกร",
  "warning": "คำเตือนวิกฤตที่ต้องเฝ้าระวังเป็นพิเศษ เช่น โรคระบาดประจำพื้นที่ หรือช่วงแล้งวิกฤต ถ้าไม่มีให้ระบุเป็นสตริงว่าง"
}}
"""

        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={
                "temperature": 0.15,
                "response_mime_type": "application/json"
            }
        )

        response = generate_content_with_retry(model, prompt)
        raw_text = response.text.strip()

        if raw_text.startswith("```json"):
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        ai_result = json.loads(raw_text)
        return jsonify({
            "success": True,
            "data": ai_result,
            "backend_signature": "AgriFuture-Gemini-v2"
        })

    except json.JSONDecodeError as e:
        return jsonify({
            "success": False,
            "error": f"[AgriFuture-Backend] AI ประมวลผลข้อมูลกลับมาคลาดเคลื่อนจากโครงสร้างมาตรฐาน: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"[AgriFuture-Backend] ระบบเกิดข้อผิดพลาดในการประมวลผล: {str(e)}"
        }), 500


# ══════════════════════════════════════════════════════════════
# 2) พยากรณ์อากาศ — /api/locations, /api/weather/<province>  (เดิมจาก Phaya.py)
# ══════════════════════════════════════════════════════════════
LOCATIONS = {
    "กรุงเทพมหานคร": {"lat": 13.7563, "lon": 100.5018},
    "เชียงใหม่": {"lat": 18.7883, "lon": 98.9853},
    "ภูเก็ต": {"lat": 7.8804, "lon": 98.3923},
    "ขอนแก่น": {"lat": 16.4419, "lon": 102.836},
    "ชลบุรี": {"lat": 13.3611, "lon": 100.9847},
    "สุราษฎร์ธานี": {"lat": 9.1382, "lon": 99.3214},
    "นครราชสีมา": {"lat": 14.9799, "lon": 102.0978},
    "เชียงราย": {"lat": 19.9105, "lon": 99.8406},
    "อุดรธานี": {"lat": 17.4138, "lon": 102.7877},
    "พระนครศรีอยุธยา": {"lat": 14.3692, "lon": 100.5877},
}

WMO_CODES = {
    0: {"label": "ท้องฟ้าแจ่มใส", "icon": "☀️"},
    1: {"label": "ส่วนใหญ่แจ่มใส", "icon": "🌤️"},
    2: {"label": "มีเมฆบางส่วน", "icon": "⛅"},
    3: {"label": "มืดครึ้ม", "icon": "☁️"},
    45: {"label": "หมอกลง", "icon": "🌫️"},
    51: {"label": "ฝนปรอยๆ เบา", "icon": "🌦️"},
    61: {"label": "ฝนเบา", "icon": "🌧️"},
    63: {"label": "ฝนปานกลาง", "icon": "🌧️"},
    65: {"label": "ฝนหนัก", "icon": "🌧️"},
    80: {"label": "ฝนตกเล็กน้อย", "icon": "🌦️"},
    81: {"label": "ฝนตกปานกลาง", "icon": "🌧️"},
    82: {"label": "ฝนตกหนัก", "icon": "⛈️"},
    95: {"label": "พายุฝนฟ้าคะนอง", "icon": "⛈️"},
    99: {"label": "พายุฝนลูกเห็บหนัก", "icon": "🌩️"},
}


def get_wmo(code):
    return WMO_CODES.get(int(code), {"label": "ไม่ทราบ", "icon": "🌡️"})


@app.route("/api/locations")
def locations():
    return jsonify({"locations": list(LOCATIONS.keys())})


@app.route("/api/weather/<province>")
def weather(province):
    loc = LOCATIONS.get(province)
    if not loc:
        return jsonify({"error": "ไม่พบจังหวัดนี้"}), 404

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={loc['lat']}&longitude={loc['lon']}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        f"precipitation_sum,windspeed_10m_max,sunrise,sunset,uv_index_max"
        f"&hourly=temperature_2m,relativehumidity_2m,weathercode,"
        f"windspeed_10m,precipitation_probability"
        f"&current_weather=true"
        f"&timezone=Asia/Bangkok"
        f"&forecast_days=7"
    )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return jsonify({"error": f"ดึงข้อมูลไม่ได้: {e}"}), 503

    now = datetime.now()
    daily = data.get("daily", {})
    cur = data.get("current_weather", {})
    hourly = data.get("hourly", {})

    today = now.strftime("%Y-%m-%d")
    cur_hour = f"{today}T{now.strftime('%H')}"
    humidity, rain_prob = 75, 0
    for i, t in enumerate(hourly.get("time", [])):
        if t.startswith(cur_hour):
            humidity = hourly.get("relativehumidity_2m", [75])[i]
            rain_prob = hourly.get("precipitation_probability", [0])[i]
            break

    forecast = []
    days_th = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"]
    months_th = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

    for i, d in enumerate(daily.get("time", [])):
        dt = datetime.strptime(d, "%Y-%m-%d")
        info = get_wmo(daily["weathercode"][i])
        forecast.append({
            "date": d,
            "day_th": "วันนี้" if i == 0 else ("พรุ่งนี้" if i == 1 else f"วัน{days_th[dt.weekday()]}"),
            "date_th": f"{dt.day} {months_th[dt.month]} {dt.year + 543}",
            "icon": info["icon"],
            "label": info["label"],
            "temp_max": round(daily["temperature_2m_max"][i] or 0),
            "temp_min": round(daily["temperature_2m_min"][i] or 0),
            "rain": round(daily.get("precipitation_sum", [0] * 7)[i] or 0, 1),
            "wind": round(daily.get("windspeed_10m_max", [0] * 7)[i] or 0),
            "uv": round(daily.get("uv_index_max", [0] * 7)[i] or 0),
            "sunrise": (daily.get("sunrise", [""])[i] or "")[-5:],
            "sunset": (daily.get("sunset", [""])[i] or "")[-5:],
        })

    hourly_out = []
    for i, t in enumerate(hourly.get("time", [])[:48]):
        if not t.startswith(today):
            continue
        h_info = get_wmo(hourly["weathercode"][i])
        hourly_out.append({
            "time": t[11:16],
            "temp": round(hourly["temperature_2m"][i] or 0),
            "icon": h_info["icon"],
            "rain_prob": hourly.get("precipitation_probability", [0] * 48)[i] or 0,
            "humidity": hourly.get("relativehumidity_2m", [75] * 48)[i] or 0,
        })

    cur_info = get_wmo(cur.get("weathercode", 0))
    updated = now.strftime(f"%d/%m/{now.year + 543} %H:%M น.")

    return jsonify({
        "province": province,
        "updated": updated,
        "source": "Open-Meteo (ECMWF/GFS) / กรมอุตุนิยมวิทยาไทย",
        "current": {
            "temp": round(cur.get("temperature", 0)),
            "windspeed": round(cur.get("windspeed", 0)),
            "icon": cur_info["icon"],
            "label": cur_info["label"],
            "humidity": humidity,
            "rain_prob": rain_prob,
            "temp_max": forecast[0]["temp_max"] if forecast else 0,
            "temp_min": forecast[0]["temp_min"] if forecast else 0,
            "sunrise": forecast[0]["sunrise"] if forecast else "--:--",
            "sunset": forecast[0]["sunset"] if forecast else "--:--",
            "uv": forecast[0]["uv"] if forecast else 0,
        },
        "forecast": forecast,
        "hourly": hourly_out,
    })


# ══════════════════════════════════════════════════════════════
# 3) แชท AI — /chat  (ปรับจาก Chat.py: เปลี่ยนจาก Ollama มาเป็น Gemini)
# ══════════════════════════════════════════════════════════════
CHAT_SYSTEM_PROMPT = """คุณคือ AgriFuture AI ผู้ช่วยด้านการเกษตรที่เชี่ยวชาญสำหรับเกษตรกรและผู้สนใจการเกษตรในประเทศไทย

คุณสามารถตอบคำถามเกี่ยวกับหัวข้อเหล่านี้เท่านั้น:
1. การเกษตรทั่วไป — การปลูกพืช การเลี้ยงสัตว์ การจัดการดิน ปุ๋ย ยาฆ่าแมลง การชลประทาน การเก็บเกี่ยว
2. เทคโนโลยีการเกษตร — Smart Farm, IoT, โดรนการเกษตร, AI/ML ในการเกษตร, เซ็นเซอร์วัดดิน/น้ำ, ระบบน้ำหยด, greenhouse อัจฉริยะ
3. ข่าวสารและข้อมูลตลาดการเกษตร — ราคาพืชผล สถานการณ์การเกษตร นโยบายเกษตร

กฎที่ต้องปฏิบัติ:
- หากผู้ใช้ถามเรื่องที่ไม่เกี่ยวข้องกับการเกษตร ให้ตอบสุภาพว่า "ขอโทษครับ ฉันตอบได้เฉพาะคำถามเกี่ยวกับการเกษตร เทคโนโลยีการเกษตร และข่าวสารการเกษตรเท่านั้น มีคำถามด้านการเกษตรที่ต้องการทราบไหมครับ?"
- ตอบเป็นภาษาไทยเสมอ ยกเว้นคำศัพท์เทคนิคที่จำเป็น
- ให้ข้อมูลที่ถูกต้อง ชัดเจน และเป็นประโยชน์จริงๆ
- ใช้ภาษาที่เข้าใจง่าย เหมาะกับเกษตรกรทั่วไป
- หากไม่แน่ใจในข้อมูล ให้บอกตรงๆ และแนะนำให้ปรึกษาผู้เชี่ยวชาญ"""

CREATOR_ANSWER = (
    "AgriFuture AI เป็นการสร้างและพัฒนาของกลุ่มนักเรียน 3 คน ห้องพิเศษ Smart-IT "
    "โรงเรียนวังน้ำเย็นวิทยาคม ที่เล็งเห็นถึงปัญหาของชาวเกษตรกรที่ประสบปัญหาทางด้าน"
    "การตัดสินใจและการวางแผนในการปลูกผลผลิต"
)

CREATOR_KEYWORDS = [
    "ใครสร้าง", "ใครเป็นคนสร้าง", "ใครพัฒนา", "ใครเป็นคนพัฒนา",
    "ผู้สร้าง", "ผู้พัฒนา", "ทีมพัฒนา", "ทีมผู้พัฒนา",
    "ใครทำ", "ใครเป็นคนทำ", "ใครออกแบบ",
    "สร้างโดยใคร", "พัฒนาโดยใคร", "ทำโดยใคร", "ออกแบบโดยใคร",
    "มาจากไหน", "เป็นของใคร", "เจ้าของระบบ",
    "who made you", "who created you", "who developed you",
    "who built you", "creator", "developer of this"
]


def is_creator_question(message: str) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(keyword.lower() in lowered for keyword in CREATOR_KEYWORDS)


def extract_user_message(data: dict) -> str:
    """แกะข้อความจากโครงสร้างอาเรย์หรือข้อความเดี่ยวตามที่ JavaScript ส่งมา"""
    if 'messages' in data and len(data['messages']) > 0:
        return data['messages'][-1].get('content', '')
    return data.get('message', data.get('prompt', ''))


def query_gemini_chat(user_message: str) -> str:
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=CHAT_SYSTEM_PROMPT,
        generation_config={"temperature": 0.7}
    )
    response = generate_content_with_retry(model, user_message)
    return (response.text or "").strip()


@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat_api():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'CORS OK'}), 200

    try:
        data = request.get_json() or {}
        user_message = extract_user_message(data)

        if not user_message:
            return jsonify({'error': 'ไม่พบข้อความคำถามจากระบบ'}), 400

        if is_creator_question(user_message):
            reply = CREATOR_ANSWER
            return jsonify({'reply': reply, 'response': reply, 'content': reply, 'status': 'success'}), 200

        if not os.environ.get("GEMINI_API_KEY"):
            return jsonify({'error': 'เซิร์ฟเวอร์ยังไม่ได้ตั้งค่า GEMINI_API_KEY'}), 500

        reply = query_gemini_chat(user_message)
        return jsonify({'reply': reply, 'response': reply, 'content': reply, 'status': 'success'}), 200

    except Exception as e:
        print("!! /chat Error !! :", str(e))
        return jsonify({'error': f'ระบบขัดข้อง: {str(e)}'}), 500


# ══════════════════════════════════════════════════════════════
# 4) วางแผนการปลูกแบบละเอียด — /api/plan  (ย้ายมาจาก Chat.py)
# ══════════════════════════════════════════════════════════════
def generate_plan_with_gemini(payload, retries=5, backoff_in_seconds=2):
    """สร้างแผนการปลูกแบบละเอียด (JSON) จากข้อมูลผลวิเคราะห์ที่ plan.js ส่งมา"""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "ไม่พบ GEMINI_API_KEY — กรุณาตั้งค่าใน Environment Variables"
        )

    crop_name       = payload.get('crop_name', '')
    province        = payload.get('province', '')
    district        = payload.get('district', '')
    budget          = payload.get('budget', '')
    area            = payload.get('area', '')
    water_source    = payload.get('water_source', '')
    planting_month  = payload.get('planting_month', '')
    success_chance  = payload.get('success_chance', '')
    success_percent = payload.get('success_percent', '')
    estimated_income = payload.get('estimated_income', '')
    roi_months      = payload.get('roi_months', '')
    pros            = payload.get('pros', [])
    cons            = payload.get('cons', [])
    tips            = payload.get('tips', [])

    prompt = f"""
คุณคือ AI ผู้เชี่ยวชาญด้านการเกษตร ทำหน้าที่วางแผนการปลูกแบบละเอียดให้เกษตรกร
โดยอิงจากผลการวิเคราะห์ที่มีอยู่แล้วต่อไปนี้:

- พืชที่จะปลูก: {crop_name}
- พื้นที่: อำเภอ {district} จังหวัด {province} (ขนาดพื้นที่: {area})
- งบประมาณ: {budget} บาท
- แหล่งน้ำ: {water_source}
- เดือนที่เริ่มปลูก: {planting_month}
- โอกาสสำเร็จ: {success_chance} ({success_percent}%)
- รายได้โดยประมาณ: {estimated_income}
- ระยะเวลาคืนทุน: {roi_months} เดือน
- ข้อดี: {', '.join(pros) if isinstance(pros, list) else pros}
- ข้อเสีย/ความเสี่ยง: {', '.join(cons) if isinstance(cons, list) else cons}
- เคล็ดลับ: {', '.join(tips) if isinstance(tips, list) else tips}

จงวางแผนการปลูกแบบละเอียด และตอบกลับเป็น JSON ภาษาไทยเท่านั้น ห้ามมีคำอธิบายอื่นนอกเหนือจาก JSON
โครงสร้างต้องตรงตามตัวอย่างนี้เป๊ะๆ:

{{
  "plan_overview": "สรุปภาพรวมแผนการปลูกทั้งหมดแบบกระชับ",
  "timeline": [
    {{ "phase": "ชื่อขั้นตอน เช่น เตรียมดิน", "duration": "ช่วงเวลา เช่น สัปดาห์ที่ 1", "description": "รายละเอียดสิ่งที่ต้องทำ" }}
  ],
  "expected_yield": {{ "amount": "ตัวเลขผลผลิตที่คาดว่าจะได้", "unit": "หน่วย เช่น กก./ไร่", "note": "หมายเหตุเพิ่มเติม" }},
  "watering_schedule": {{ "times_total": "จำนวนครั้งรวมตลอดฤดูปลูก", "frequency_per_week": "ความถี่ต่อสัปดาห์", "note": "หมายเหตุการให้น้ำ" }},
  "equipment": ["รายการอุปกรณ์ที่จำเป็น"],
  "fertilizer_plan": [
    {{ "stage": "ช่วงการเจริญเติบโต", "type": "สูตร/ชนิดปุ๋ย", "amount": "ปริมาณ", "note": "หมายเหตุ" }}
  ],
  "final_advice": "คำแนะนำปิดท้ายจาก AI"
}}
"""

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "temperature": 0.3,
            "response_mime_type": "application/json"
        }
    )

    for i in range(retries):
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI ประมวลผลข้อมูลกลับมาคลาดเคลื่อนจากโครงสร้างมาตรฐาน: {str(e)}")
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(backoff_in_seconds * (2 ** i))
                continue
            raise RuntimeError(f"เรียก Gemini API ไม่สำเร็จ: {str(e)}")


@app.route('/api/plan', methods=['POST', 'OPTIONS'])
def plan_api():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'CORS OK'}), 200
    try:
        if not os.environ.get("GEMINI_API_KEY"):
            return jsonify({'success': False, 'error': 'เซิร์ฟเวอร์ยังไม่ได้ตั้งค่า GEMINI_API_KEY'}), 500

        data = request.get_json() or {}
        if not data.get('crop_name'):
            return jsonify({'success': False, 'error': 'ไม่พบข้อมูลพืชที่จะวางแผนปลูก'}), 400

        plan_data = generate_plan_with_gemini(data)
        return jsonify({
            'success': True,
            'data': plan_data
        }), 200

    except RuntimeError as e:
        print("!! Gemini /api/plan Error !! :", str(e))
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        print("!! /api/plan Error !! :", str(e))
        return jsonify({'success': False, 'error': f'ระบบขัดข้อง: {str(e)}'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'online',
        'msg': 'AgriFuture combined API ready — /api/analyze, /chat, /api/plan',
        'gemini_configured': bool(os.environ.get("GEMINI_API_KEY"))
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)
