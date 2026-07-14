import os
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# อนุญาต CORS สำหรับทุกโดเมนและรองรับ Content-Type: application/json ข้ามโดเมนได้ 100%
CORS(app, resources={r"/api/*": {"origins": "*"}})

# กำหนด API Key ของ Gemini (ใช้ตัวแปรแวดล้อมเดียวกับ app.py)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


# ฟังก์ชันช่วยลองใหม่หากติด Rate Limit (429) ด้วยวิธี Exponential Backoff
def generate_content_with_retry(model, prompt, retries=5, backoff_in_seconds=2):
    for i in range(retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(backoff_in_seconds * (2 ** i))
                continue
            raise e


@app.route('/api/plan', methods=['POST'])
def create_plan():
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "[AgriFuture-Plan] ไม่พบข้อมูลที่ส่งมาจากหน้าบ้าน (Body ว่างเปล่า)"}), 400

        # ดึงข้อมูลของพืชที่เลือกไว้จากหน้าผลวิเคราะห์ (result.html) ที่ผู้ใช้เลือกผ่าน picker
        crop_name = data.get('crop_name', '')
        province = data.get('province', '')
        district = data.get('district', '')
        budget = data.get('budget', '')
        area = data.get('area', '')
        water_source = data.get('water_source', '')
        planting_month = data.get('planting_month', '')
        success_chance = data.get('success_chance', '')
        success_percent = data.get('success_percent', '')
        estimated_income = data.get('estimated_income', '')
        roi_months = data.get('roi_months', '')
        pros = data.get('pros', [])
        cons = data.get('cons', [])
        tips = data.get('tips', [])

        if not crop_name:
            return jsonify({"success": False, "error": "[AgriFuture-Plan] ไม่พบชื่อพืชที่จะวางแผนการปลูก"}), 400

        if not os.environ.get("GEMINI_API_KEY"):
            return jsonify({"success": False, "error": "[AgriFuture-Plan] ไม่พบ GEMINI_API_KEY กรุณาตั้งค่าในไฟล์ .env"}), 500

        # ประกอบ Prompt ส่งให้ AI พร้อมกำหนดสเปค JSON ที่ต้องการอย่างละเอียด
        prompt = f"""
คุณคือ AI ที่ปรึกษาการเกษตรอัจฉริยะ (AgriFuture AI) หน้าที่ของคุณคือวางแผนการปลูกแบบละเอียดให้เกษตรกร
โดยอ้างอิงจากผลวิเคราะห์ที่มีอยู่แล้วต่อไปนี้ (ห้ามวิเคราะห์ใหม่ ให้นำไปต่อยอดเป็นแผนปฏิบัติจริงเท่านั้น):

- พืชที่จะปลูก: {crop_name}
- พื้นที่ปลูก: อำเภอ {district} จังหวัด {province} (ขนาดพื้นที่: {area})
- งบประมาณ: {budget} บาท
- แหล่งน้ำที่เข้าถึงได้: {water_source}
- ช่วงเวลาที่จะเริ่มปลูก: เดือน {planting_month}
- โอกาสสำเร็จจากผลวิเคราะห์เดิม: {success_chance} ({success_percent}%)
- รายได้ประมาณการ: {estimated_income} บาท/ไร่/ปี
- ระยะคืนทุนโดยประมาณ: {roi_months} เดือน
- ข้อดีที่เคยระบุไว้: {', '.join(pros) if pros else '-'}
- ความเสี่ยงที่เคยระบุไว้: {', '.join(cons) if cons else '-'}
- เคล็ดลับที่เคยระบุไว้: {', '.join(tips) if tips else '-'}

จงจัดทำ "แผนการปลูก" ที่นำไปปฏิบัติได้จริงทันที ตอบกลับมาเป็นรูปแบบโครงสร้าง JSON ภาษาไทยเท่านั้น
ห้ามมีคำอธิบายอื่นนอกเหนือจาก JSON โครงสร้างต้องตรงตามรูปแบบตัวอย่างนี้เป๊ะๆ:

{{
  "plan_overview": "สรุปภาพรวมแผนการปลูกพืชนี้แบบกระชับ 2-3 ประโยค",
  "timeline": [
    {{
      "phase": "ชื่อขั้นตอน เช่น เตรียมดิน / เพาะกล้า / ย้ายปลูก / ดูแลระยะเจริญเติบโต / เก็บเกี่ยว",
      "duration": "ระยะเวลาโดยประมาณ เช่น สัปดาห์ที่ 1-2",
      "description": "รายละเอียดสิ่งที่ต้องทำในขั้นตอนนี้"
    }}
  ],
  "expected_yield": {{
    "amount": "ปริมาณผลผลิตที่คาดว่าจะเก็บได้ เช่น 800-1000",
    "unit": "หน่วย เช่น กก./ไร่ หรือ ตัน/ไร่",
    "note": "คำอธิบายเพิ่มเติมเกี่ยวกับผลผลิตที่คาดว่าจะได้"
  }},
  "equipment": [
    "รายการอุปกรณ์ที่จำเป็นต้องใช้ ข้อที่ 1",
    "รายการอุปกรณ์ที่จำเป็นต้องใช้ ข้อที่ 2"
  ],
  "fertilizer_plan": [
    {{
      "stage": "ช่วงการเจริญเติบโตที่ต้องใส่ปุ๋ย เช่น ช่วงเตรียมดิน",
      "type": "สูตรปุ๋ยหรือชนิดปุ๋ยที่แนะนำ เช่น 15-15-15",
      "amount": "ปริมาณที่ใช้ต่อไร่ เช่น 25 กก./ไร่",
      "note": "ข้อควรระวังหรือวิธีใส่"
    }}
  ],
  "watering_schedule": {{
    "frequency_per_week": "ความถี่ในการให้น้ำต่อสัปดาห์ เช่น 3",
    "times_total": "จำนวนครั้งรวมโดยประมาณตลอดฤดูปลูกจนเก็บเกี่ยว เช่น 24",
    "note": "คำอธิบายรอบการให้น้ำ เช่น ควรเพิ่มความถี่ในช่วงออกดอกติดผล หรือลดในฤดูฝน"
  }},
  "final_advice": "คำแนะนำปิดท้ายจาก AI สรุปภาพรวมทั้งหมดเพื่อความมั่นใจของเกษตรกรก่อนเริ่มลงมือปลูกจริง"
}}
"""

        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )

        response = generate_content_with_retry(model, prompt)
        raw_text = response.text.strip()

        # ตรวจเช็คเพื่อความปลอดภัย หากมี Markdown backticks ห่อหุ้มมาให้ทำการถอดออก
        if raw_text.startswith("```json"):
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        ai_plan = json.loads(raw_text)

        return jsonify({
            "success": True,
            "data": ai_plan,
            "backend_signature": "AgriFuture-Gemini-Plan-v1"
        })

    except json.JSONDecodeError as e:
        return jsonify({
            "success": False,
            "error": f"[AgriFuture-Plan] AI ประมวลผลข้อมูลกลับมาคลาดเคลื่อนจากโครงสร้างมาตรฐาน: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"[AgriFuture-Plan] ระบบเกิดข้อผิดพลาดในการประมวลผล: {str(e)}"
        }), 500


if __name__ == '__main__':
    # ใช้ Port 5002 เพื่อไม่ให้ชนกับ app.py (5001) และ costcalc.py (สมมติว่าใช้ port อื่นอยู่แล้ว)
    # หากในเครื่องของคุณ costcalc.py ใช้ port 5002 อยู่แล้ว ให้เปลี่ยนเลข port ตรงนี้เป็นค่าอื่น
    # และแก้ไขค่า PLAN_API_PORT ในไฟล์ plan.js ให้ตรงกัน
    app.run(host='0.0.0.0', port=5000, debug=True)
