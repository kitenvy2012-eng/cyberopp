# Task for Antigravity — audited baseline at `6c4db98`

เราแบ่งงานผ่าน repo นี้ ไม่ได้คุยกันตรง ๆ เอกสารนี้คือ (1) ผลตรวจว่าของที่ทำไปหลุดตรงไหน และ (2) งานถัดไปที่ควรทำ

---

## 1. ผลตรวจ Phase 1 — ผ่าน ไม่หลุด

| เกณฑ์ | ผล |
|---|---|
| Test suite | 72/72 ผ่าน |
| §57 PDF เก่าปี 2024 ต้องไม่โผล่เป็นโอกาสวันนี้ | **PASS** |
| §58 ประกาศ 1 ก.ย. deadline 20 ก.ย. ต้องโผล่ | **PASS** |
| §59 งานที่ประกาศผู้ชนะแล้วต้องไม่โผล่ | **PASS** |
| §12 `announcement_date` แยกจาก `first_seen_at` | **PASS** |
| Source ซ้อนกันระหว่าง `scraper_sources` กับ `sources` | ไม่มี drift (11 = 11) |
| §15 `procurement_awards` / §17 `procurement_event_versions` | ยังไม่ถึงเฟส |

**สิ่งที่เพิ่งเพิ่มเข้ามาฝั่ง backend (commit `9504710`)** — อย่าทำซ้ำ:
- `bid_notice_status = "AWARDED"` เซ็ตจากหลักฐานที่เก็บไว้ (`project_detail.contract[].winner.name`) และมี pass ตอนบูตย้อนซ่อมข้อมูลเดิม
- มุมมองหลักตัด AWARDED ออก → **191 เหลือ 71** เรียกดูได้ด้วย `include_awarded=true` / `opportunity_scope=AWARDED`
- `opportunity_scope=AWARDED` ถูกยกเว้นจากตัวกรองนี้แล้ว ไม่งั้นมันคืนค่าว่าง

---

## 2. ปัญหาที่เจอ — Buyer Coverage ไปไม่ถึง 80% ด้วยรายชื่อชุดนี้

```
§65 Buyer Coverage Rate = 10/25 = 40%   (เป้า >= 80%)
```

buyer 15 รายที่ยังไม่มี source แบ่งเป็นสองกลุ่มที่ต้องปฏิบัติต่างกัน:

**กลุ่ม A — พิสูจน์แล้วว่าไม่มีทางได้ (10 ราย)**
AIS, True, KBANK, SCB, BBL, TTB, CP All, Central Retail, WHA, Bitkub, BDMS

`backend/discover_procurement_pages.py` ไล่ 40 บริษัทแล้ว **เอกชน 0 จาก 24 รายมีบอร์ดประกาศสาธารณะ** เพราะ พ.ร.บ.จัดซื้อจัดจ้างฯ 2560 บังคับเฉพาะหน่วยงานรัฐ เอกชนใช้ทะเบียนคู่ค้าแล้วส่ง RFP ตรง — **การไล่หา URL เพิ่มจะไม่ทำให้ตัวเลขนี้ขึ้น**

**กลุ่ม B — ได้แน่ ควรทำก่อน (5 ราย)**
NT, KTB, PTT, MEA — เป็นรัฐวิสาหกิจ/ธนาคารรัฐ ที่**ต้องประกาศตามกฎหมาย** และมีหน้าจริง

---

## 3. งานถัดไป (เรียงตามผลลัพธ์ต่อผู้ใช้)

### 3.1 แก้นิยาม Coverage ให้ตรงความจริง — ทำก่อน

ตอนนี้ coverage นับเฉพาะ source ที่ผูกกับ buyer โดยตรง แต่ **e-GP ครอบคลุมหน่วยงานรัฐและรัฐวิสาหกิจทุกแห่งตามกฎหมายอยู่แล้ว** — NT, KTB, PTT, MEA, BOT, SEC, EGAT, PEA อยู่ใน e-GP ทั้งหมด

ให้คิด coverage เป็น:

```
covered = มี source ผูกตรง
        OR (company_type ∈ {GOVERNMENT, STATE_ENTERPRISE} และมี tender ใน e-GP ที่ชื่อหน่วยงานตรงกับ buyer)
```

ต้องแมป `Tender.agency` ↔ `Buyer.name` ให้ได้ (ตอนนี้ e-GP source ยังไม่ผูก buyer เพราะมันครอบหลาย buyer — อย่าฝืนผูกกับ buyer เดียว)

ผลที่ควรได้: coverage ขึ้นจาก 40% เป็นระดับที่สะท้อนความจริง โดยไม่ต้องแต่งตัวเลข

### 3.2 ตั้ง `procurement_coverage_status` จากของจริง ไม่ใช่ค่าที่พิมพ์ไว้

ตอนนี้ `INITIAL_BUYERS` ใส่ค่า `HIGH/MEDIUM/LOW` ไว้ด้วยมือ เช่น SCG = `MEDIUM` ทั้งที่ `scg.com/th/procurement/` redirect ไปหน้าแรก (ไม่มีหน้านั้นจริง) — ค่านี้ต้องคำนวณจาก source ที่ verify แล้ว ไม่งั้นหน้า Buyer Watch จะโกหก

เสนอ:
```
HIGH    = มี source ที่ health HEALTHY และมี tender เข้ามาใน 90 วัน
MEDIUM  = มี source ที่ verify แล้ว แต่ยังไม่มี tender ใหม่
LOW     = ครอบด้วย e-GP เท่านั้น
UNKNOWN = ยังไม่ได้ตรวจ
```

### 3.3 กลุ่ม B — เพิ่ม source ให้ 5 รายที่ทำได้

ก่อนเพิ่มทุกครั้ง ให้รัน:
```bash
PYTHONPATH=. backend/venv/bin/python backend/discover_procurement_pages.py --json findings.json
```
แล้วใส่ `verified_note` บอกว่าเห็นอะไร **ห้ามใส่ URL ที่ยังไม่ได้ยิงดู** — เคส SCG คือตัวอย่างที่ source ถูกเปิดใช้งานทั้งที่หน้าไม่มีอยู่จริง

### 3.4 อย่าเพิ่ง — Phase 5 (versioning/awards) และ Search Discovery

`procurement_awards` และ `procurement_event_versions` ยังไม่จำเป็นจนกว่า coverage จะนิ่ง ส่วน Search Discovery (§26) มีความเสี่ยงสูงที่จะดึงเอกสารเก่ามาแสดงเป็นของใหม่ ซึ่งเป็นปัญหาเดิมที่เพิ่งแก้ไป

---

## 4. กติกาของ repo นี้

1. **ห้ามแต่งข้อมูล** — ฟิลด์ที่ต้นทางไม่ให้ต้องเป็น `null` ไม่ใช่ค่าเดา
2. **เพิ่ม source ต้องพิสูจน์ก่อน** — ยิง URL ดูว่าไม่ redirect ไปหน้าแรก
3. **เคารพ robots.txt** — crawler ตั้ง fail-closed; JobsDB ห้ามแตะ (robots ระบุ `anthropic-ai`/`GPTBot` ไว้ชัด), JobTopGun/JobBKK อนุญาต `/jobs/`
4. **รันเทสต์ก่อน commit**: `PYTHONPATH=. backend/venv/bin/python -m unittest discover -s backend/tests`
5. **อย่ารื้อทีเดียวจบ** — แต่ละ commit ต้อง deploy ได้


---

## 5. ผลจากการ deploy จริง (commit `69b2ea6`) — ข้อค้นพบสำคัญ

เปิด `BACKFILL_ENRICH_DETAILS=true` บน Render แล้วให้ backfill ดึง `project_detail` ครบทุกรายการ ผลคือ:

```
e-GP ในกรอบ 1 ปี = 166 รายการ
มีชื่อผู้ชนะในหลักฐานแล้ว = 166 รายการ  (100%)
เหลือเป็นโอกาส = 0
```

**e-GP / GovSpending คือบันทึกการใช้จ่ายที่จบแล้ว ไม่ใช่กระดานประกาศเชิญชวน** กว่าโครงการจะมี `announce_date` โผล่ในฟีดนี้ การแข่งขันมักจบไปแล้ว

ผลต่อการออกแบบ:
- **อย่านับ e-GP เป็นแหล่งของ "โอกาส"** ให้ใช้เป็นข้อมูลตลาด (ใครชนะ ราคาเท่าไร ซื้อบ่อยแค่ไหน) ซึ่งมีค่ามากสำหรับ §64 Sales Intelligence
- **โอกาสจริงมาจากแหล่งเชิญชวนเท่านั้น** — ป.ป.ส., DGA, ETDA, PEA, ธปท. ที่ลงเอกสารประกาศพร้อมวันยื่นซอง
- ตอนนี้บนของจริงเหลือ **7 รายการที่ยังยื่นได้** (ป.ป.ส. 6 + ETDA 1) โดย 4 รายการมีวันปิดรับจริง 14 และ 21 ก.ย.

ข้อเสนอต่อ §3.1: ตอน map `Tender.agency` ↔ `Buyer.name` เพื่อคิด coverage ให้แยกให้ชัดว่า buyer นั้น "ครอบด้วย e-GP" (= เห็นประวัติการซื้อ) ต่างจาก "มีแหล่งเชิญชวน" (= เห็นโอกาสก่อนปิดรับ) สองอย่างนี้มีค่าต่อผู้ใช้ไม่เท่ากัน
