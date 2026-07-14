"""
AgriFuture AI — Python Flask Backend (Gemini Edition)
เวอร์ชันรวมมิตร: เปิดประตูรับทั้ง /chat และ /api/analyze เพื่อแก้ปัญหา CORS 100%
อัปเดต: เปลี่ยนจาก Ollama (local) กลับมาใช้ Google Gemini API
"""

import os
import json
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env อัตโนมัติ
load_dotenv()

app = Flask(__name__)

# ตั้งค่าปลดล็อกระบบความปลอดภัย CORS ขั้นสูงสุดสำหรับทุกช่องทาง
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# ── คอนฟิกการเชื่อมต่อ Gemini ───────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ข้อความข้อกำหนดพฤติกรรมการตอบของบอท
SYSTEM_PROMPT = """คุณคือ AgriFuture AI ผู้ช่วยด้านการเกษตรที่เชี่ยวชาญสำหรับเกษตรกรและผู้สนใจการเกษตรในประเทศไทย

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

# ── คำตอบสำเร็จรูปเมื่อมีคนถามถึงผู้สร้าง/ผู้พัฒนา ────────────────────────────
CREATOR_ANSWER = (
    "AgriFuture AI เป็นการสร้างและพัฒนาของกลุ่มนักเรียน 3 คน ห้องพิเศษ Smart-IT "
    "โรงเรียนวังน้ำเย็นวิทยาคม ที่เล็งเห็นถึงปัญหาของชาวเกษตรกรที่ประสบปัญหาทางด้าน"
    "การตัดสินใจและการวางแผนในการปลูกผลผลิต"
)

# คำ/ประโยคที่เข้าข่ายถามถึงผู้สร้าง ผู้พัฒนา หรือที่มาของระบบ
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
    """ตรวจสอบว่าข้อความเข้าข่ายถามเจาะจงถึงผู้สร้าง/ผู้พัฒนาของระบบหรือไม่"""
    if not message:
        return False
    lowered = message.lower()
    return any(keyword.lower() in lowered for keyword in CREATOR_KEYWORDS)


def query_gemini_model(user_message, retries=5, backoff_in_seconds=2):
    """ฟังก์ชันส่งคำถามไปประมวลผลกับ Gemini API พร้อม retry เมื่อเจอ Rate Limit (429)"""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "ไม่พบ GEMINI_API_KEY — กรุณาตั้งค่าในไฟล์ .env เช่น GEMINI_API_KEY=your_key_here"
        )

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"temperature": 0.7}
    )

    for i in range(retries):
        try:
            response = model.generate_content(user_message)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                # เพิ่มระยะเวลาดีเลย์ขึ้นทีละเท่าตัว
                time.sleep(backoff_in_seconds * (2 ** i))
                continue
            raise RuntimeError(f"เรียก Gemini API ไม่สำเร็จ: {str(e)}")


def handle_chat_request():
    """ฟังก์ชันกลางที่ใช้ร่วมกันทั้ง /chat และ /api/analyze"""
    data = request.get_json() or {}
    user_message = ""

    # แกะข้อความจากโครงสร้างอาเรย์หรือข้อความเดี่ยวตามที่ JavaScript ส่งมา
    if 'messages' in data and len(data['messages']) > 0:
        user_message = data['messages'][-1].get('content', '')
    else:
        user_message = data.get('message', data.get('prompt', ''))

    if not user_message:
        return jsonify({'error': 'ไม่พบข้อความคำถามจากระบบ'}), 400

    # ── เช็คก่อน: ถ้าถามถึงผู้สร้าง/ผู้พัฒนา ตอบทันทีโดยไม่ต้องเรียกโมเดล ──
    if is_creator_question(user_message):
        reply = CREATOR_ANSWER
        return jsonify({
            'reply': reply,
            'response': reply,
            'content': reply,
            'status': 'success'
        }), 200

    reply = query_gemini_model(user_message)

    # ส่งค่าข้อมูลกลับในทุกชื่อตัวแปรที่หน้าเว็บอาจจะแกะอ่าน
    return jsonify({
        'reply': reply,
        'response': reply,
        'content': reply,
        'status': 'success'
    }), 200


def generate_plan_with_gemini(payload, retries=5, backoff_in_seconds=2):
    """สร้างแผนการปลูกแบบละเอียด (JSON) จากข้อมูลผลวิเคราะห์ที่ plan.js ส่งมา"""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "ไม่พบ GEMINI_API_KEY — กรุณาตั้งค่าในไฟล์ .env เช่น GEMINI_API_KEY=your_key_here"
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
        GEMINI_MODEL,
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


# ── ประตูทางเข้าพอร์ตที่ 3: สำหรับหน้า plan.html ที่ยิงหา /api/plan ─────────
@app.route('/api/plan', methods=['POST', 'OPTIONS'])
def plan_api():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'CORS OK'}), 200
    try:
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


# ── ประตูทางเข้าพอร์ตที่ 1: สำหรับหน้าเว็บที่ยิงหา /chat ─────────────────────
@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat_api():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'CORS OK'}), 200
    try:
        return handle_chat_request()
    except RuntimeError as e:
        print("!! Gemini /chat Error !! :", str(e))
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        print("!! /chat Error !! :", str(e))
        return jsonify({'error': f'ระบบขัดข้อง: {str(e)}'}), 500


# ── ประตูทางเข้าพอร์ตที่ 2: สำหรับหน้าเว็บที่ยิงหา /api/analyze ────────────────
@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze_api():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'CORS OK'}), 200
    try:
        return handle_chat_request()
    except RuntimeError as e:
        print("!! Gemini /api/analyze Error !! :", str(e))
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        print("!! /api/analyze Error !! :", str(e))
        return jsonify({'error': f'ระบบขัดข้อง: {str(e)}'}), 500


# ── หน้าเช็คสถานะเซิร์ฟเวอร์ ──────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'online',
        'msg': 'AgriFuture API (Gemini Edition) — /chat, /api/analyze, /api/plan Ready',
        'gemini_key_configured': bool(GEMINI_API_KEY),
        'model': GEMINI_MODEL
    })


if __name__ == '__main__':
    print("=" * 60)
    print(" AgriFuture AI — Backend (Gemini Edition)")
    print(f" Gemini Model : {GEMINI_MODEL}")
    print(f" API Key ตั้งค่าแล้ว : {'ใช่' if GEMINI_API_KEY else 'ไม่ — ต้องตั้งใน .env'}")
    print(" พร้อมทำงานต้อนรับหน้าต่างเว็บทั้งช่องทาง /chat, /api/analyze และ /api/plan")
    print("=" * 60)
    app.run(debug=True, port=5000)
