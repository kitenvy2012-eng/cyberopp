# Deploy: Netlify (dashboard) + container host (backend)

## ที่ deploy ไว้แล้ว

| | URL |
|---|---|
| Dashboard (Netlify) | <https://cyberopps.netlify.app> |
| Backend (Render, free) | <https://cyberwatch-api-r6p8.onrender.com> |
| Repo | <https://github.com/kitenvy2012-eng/cyberopp> |

Netlify ใช้ **Drop (อัปโหลด zip)** ไม่ได้ต่อ Git จึงไม่มี auto-deploy — อัปเดตหน้าเว็บด้วยการ build แล้วอัปโหลดใหม่ (วิธี B ด้านล่าง) Render ดึงจาก public repo URL เช่นกัน ต้องกด **Manual Deploy → Deploy latest commit** หลัง push

ถ้าต้องการ auto-deploy ทั้งสองที่ ต้องกด authorize ให้ Netlify/Render เข้าถึง GitHub เอง (ผมไม่กดให้ เพราะเป็นการให้สิทธิ์แอปภายนอกเข้าบัญชีคุณ)


Netlify รันได้แค่ static file กับ JS/Go function — รัน FastAPI, เขียน SQLite หรือรัน background scheduler **ไม่ได้** สถาปัตยกรรมที่ใช้จึงเป็น:

```
เบราว์เซอร์ ──► Netlify (React static)
                  │  /api/*  proxy (ไฟล์ _redirects)
                  ▼
             Backend host (Docker: FastAPI + SQLite บน volume)
                  │
                  ▼
             e-GP / ธปท. / PEA / กฟผ. / DGA / ETDA / สกมช.
```

เบราว์เซอร์เห็น origin เดียวคือ Netlify จึง **ไม่มีปัญหา CORS และไม่มี mixed content** และ URL ของ backend ไม่ถูกฝังลงใน bundle

> ต้อง deploy backend ก่อนเสมอ เพราะขั้นตอน build ของ frontend ต้องใช้ URL ของ backend

---

## ขั้นที่ 1 — Deploy backend

ใช้ `Dockerfile` ที่ root ได้กับ Render, Railway, Fly.io, Google Cloud Run หรือ VPS ที่มี Docker

### Render (มี `render.yaml` ให้แล้ว)

1. <https://dashboard.render.com/blueprints> → **New Blueprint Instance** → เลือก repo นี้
2. Render อ่าน `render.yaml` เอง — ตั้งเป็น **plan free** ไว้ จึงไม่มีค่าใช้จ่าย
3. รอจน health check ที่ `/api/health` เขียว แล้วจดโดเมนไว้ เช่น `https://cyberwatch-api.onrender.com`

**free plan แลกกับอะไร**

| | free | starter (เสียเงิน) |
|---|---|---|
| instance หลับหลังไม่มี traffic ~15 นาที | ใช่ — ไม่สแกนตามรอบตอนหลับ | ไม่หลับ |
| disk เก็บข้อมูลถาวร | ไม่มี | มี (เพิ่ม `disk:` ใน `render.yaml`) |
| ข้อมูลที่ scrape มา | หายตอน restart; ดึงซ้ำได้เฉพาะสิ่งที่ต้นทางยังเผยแพร่ ประวัติพบครั้งแรกกู้ไม่ได้ | อยู่ถาวรเมื่อมี disk |
| bookmark / pipeline / โน้ตที่พิมพ์เอง | **หายถาวร** | อยู่ถาวร |

ระบบติดตามความสดและเก็บประวัติจำเป็นต้องมีพื้นที่เก็บข้อมูลถาวรและตัวสแกนที่รันตามรอบได้ ไม่ควรถือว่า free instance ที่หลับและล้าง SQLite รองรับเงื่อนไขนี้แล้ว การเปลี่ยนแพ็กเกจต้องให้เจ้าของบัญชีอนุมัติก่อน

### ทางเลือกอื่น

| Host | สิ่งที่ต้องตั้งเอง |
|---|---|
| Railway | เพิ่ม Volume mount ที่ `/data` และตั้ง `DATABASE_URL=sqlite:////data/cyber_opp.db` |
| Fly.io | `fly launch --dockerfile Dockerfile` แล้ว `fly volumes create data --size 5` + mount `/data` |
| Cloud Run | ต้องต่อ Cloud Storage FUSE หรือย้ายไป Cloud SQL เพราะ filesystem ไม่ persist |
| VPS | `docker build -t cyberwatch . && docker run -d -p 8000:8000 -v /srv/cyberwatch:/data cyberwatch` |

### ตัวแปรสภาพแวดล้อมของ backend

| ตัวแปร | ค่า | จำเป็น |
|---|---|---|
| `DATABASE_URL` | `sqlite:////data/cyber_opp.db` (4 slash = absolute path) | ✅ |
| `SCAN_INTERVAL_MINUTES` | `180` แนะนำสำหรับ production (ค่า default 30 ถี่เกินไปสำหรับ API สาธารณะ) | – |
| `CORS_ORIGINS` | เว้นว่างไว้เมื่อใช้ proxy; ตั้งเป็น origin ของ Netlify เฉพาะเมื่อเรียก API ตรง | – |
| `BACKFILL_ON_EMPTY` | `false` เป็นค่าเริ่มต้น: ดึงประกาศปัจจุบันก่อน เปิด `true` เฉพาะเมื่อต้องการประวัติ e-GP เพิ่ม | – |
| `BACKFILL_YEARS_BACK` | จำนวนปีงบที่กวาดตอนเติมครั้งแรก (default `12`) | – |
| `SCAN_SOURCE_TYPES` | จำกัดรอบสแกนตามเวลาให้เหลือเฉพาะแหล่งที่ลงเอกสารเชิญชวน เช่น `ONCB,GOVERNMENT,BOT,STATE_ENTERPRISE,NCSA` เว้นว่าง = สแกนทุกแหล่ง | – |
| `DATA_GO_TH_API_KEY` | key จาก <https://opend.data.go.th/register_api> | – |

> **`/data` ต้องเป็น volume จริง** ถ้าไม่ mount ฐานข้อมูลจะอยู่ในคอนเทนเนอร์และหายทุกครั้งที่ redeploy

### เติมข้อมูลครั้งแรก

image ไม่ได้ใส่ไฟล์ `.db` มาด้วย (อยู่ใน `.dockerignore`) ฐานใหม่จึงว่างเปล่า เลือกทางใดทางหนึ่ง:

**ก. ดึงแหล่งประกาศปัจจุบันตอนเริ่มระบบ** (ค่าเริ่มต้นของโค้ด)

แอปสแกน `SCAN_SOURCE_TYPES` แบบ background หลังบูตโดยไม่รอประวัติ e-GP ค่าแนะนำคือ `ONCB,GOVERNMENT,CORPORATE,CUSTOM_WEB,NCSA,STATE_ENTERPRISE,BOT` (วัดจริงจากฐานว่าง: 8 นาที ได้ 103 รายการ ถ้าตัด NCSA/STATE_ENTERPRISE/BOT ออกจะเหลือ 24) แหล่งใดดึงไม่ได้จะแสดงสถานะตามจริง ไม่เติมรายการจำลอง ถ้าตั้ง `BACKFILL_ON_EMPTY=true` และฐานว่าง จึงกวาดประวัติเพิ่มหลังรอบแรก ไม่รับประกันระยะเวลา

สำหรับ Render service เดิม ต้องแก้ Environment `BACKFILL_ON_EMPTY=false` เองด้วย การเปลี่ยน `render.yaml` ไม่ได้ยืนยันว่าค่าของ service ที่สร้างไว้แล้วเปลี่ยนตาม

**ข. สั่งเองผ่าน shell ของ host** ถ้าอยากคุมเวลาเอง:

```bash
python backend/backfill_egp.py --years-back 12
```

ใช้เวลาราว 2 นาที จากนั้น scheduler ดูแลต่อเอง ธปท. จะไล่เก็บครบภายใน 2–3 รอบสแกน (หน้าที่ CDN ยังไม่แคชจะถูกยกไปรอบถัดไป — ดูเหตุผลใน README)

**ค. อัปโหลดฐานที่มีอยู่แล้ว** คัดลอก `cyber_opp.db` (108 MB) ขึ้นไปที่ `/data/cyber_opp.db` ผ่านเครื่องมือของ host — ไฟล์นี้ไม่ได้อยู่ใน git เพราะเกินลิมิต 100 MB ของ GitHub

ตรวจว่าใช้ได้:

```bash
curl https://your-backend-host.example.com/api/health
curl https://your-backend-host.example.com/api/stats
```

---

## ขั้นที่ 2 — Deploy dashboard ขึ้น Netlify

### วิธี A: ต่อกับ Git (แนะนำ — deploy อัตโนมัติทุก push)

1. Netlify → **Add new site** → **Import an existing project** → เลือก repo
2. Netlify อ่าน `netlify.toml` เอง (base `frontend`, publish `dist`) **ไม่ต้องแก้ build settings**
3. **Site configuration → Environment variables** → เพิ่ม:

   | Key | Value |
   |---|---|
   | `API_PROXY_TARGET` | `https://your-backend-host.example.com` (ไม่ต้องมี `/api` และไม่ต้องมี `/` ปิดท้าย) |

4. **Deploy site**

ถ้าลืมตั้ง `API_PROXY_TARGET` build จะ **ล้มทันทีพร้อมข้อความบอกวิธีแก้** ไม่ปล่อยเว็บที่ยิง API แล้ว 404 ขึ้นไป

### วิธี B: อัปโหลดโฟลเดอร์เอง (drag & drop)

build ที่เครื่องโดยใส่ URL backend เข้าไป:

```bash
cd frontend
npm ci
API_PROXY_TARGET=https://your-backend-host.example.com npm run build:netlify
```

แล้วลากโฟลเดอร์ `frontend/dist` ไปวางที่ <https://app.netlify.com/drop>

หรือใช้ CLI:

```bash
npx netlify-cli deploy --dir=frontend/dist --prod
```

> `dist/_redirects` ต้องติดไปด้วยเสมอ (`npm run build:netlify` สร้างให้) ถ้าใช้ `npm run build` เฉย ๆ จะไม่มีไฟล์นี้ และ `/api/*` จะไม่ถูก proxy

ตรวจว่าใช้ได้: เปิดเว็บ Netlify แล้วดูว่าตัวเลข "ระเบียนจัดซื้อทั้งหมด" ขึ้นตรงกับ `/api/stats`

---

## ทางเลือก: เรียก backend ตรงโดยไม่ผ่าน proxy

ถ้าไม่อยากให้ traffic วิ่งผ่าน Netlify (ประหยัด bandwidth quota) ให้ build ด้วย:

```bash
VITE_API_BASE=https://your-backend-host.example.com/api npm run build
```

แล้ว **ต้อง** ตั้งที่ backend: `CORS_ORIGINS=https://your-site.netlify.app`

ข้อแลกเปลี่ยน: URL ของ backend จะอยู่ใน bundle และทุก request มี preflight เพิ่ม

---

## ข้อจำกัดที่ต้องรู้ก่อน deploy

- **instance ที่หลับได้จะไม่สแกน** — free tier ของ Render/Railway จะ spin down เมื่อไม่มี traffic ทำให้ APScheduler หยุด ถ้าต้องการสแกนตามรอบจริงต้องใช้ instance ที่ไม่หลับ หรือย้ายไปใช้ cron ของ host ยิง `POST /api/scan`
- **free tier ตื่นช้ากว่าที่ proxy รอไหว** — Render cold start ใช้ 50+ วินาที ส่วน proxy ของ Netlify ยอมรอสั้นกว่านั้น เปิดเว็บครั้งแรกหลังหลับจึงเจอ 502 กด refresh อีกครั้งจะติด นี่เป็นอาการของ free plan ล้วน ๆ แก้ได้ด้วยการขึ้น plan ที่ไม่หลับ
- **first-run backfill ต้องเล็กพอกับเครื่อง** — เคยตั้ง 12 ปีแล้ว process ถูกฆ่ากลางคันตอนบันทึกรายการที่ 2,600 จาก 6,830 และเพราะ free plan ไม่มี disk การ restart จึงเจอฐานว่างแล้วเริ่มใหม่ วนไม่จบ ค่าเริ่มต้นตอนนี้คือ 2 ปี ปิด enrichment ซึ่งจบใน ~45 วินาที ถ้าจะเอาครบ 12 ปีให้รัน `backend/backfill_egp.py` ตอน service ขึ้นแล้ว และควรมี disk
- **ใช้ worker เดียวเท่านั้น** — `Dockerfile` ตั้ง `--workers 1` ไว้ เพราะตัวล็อกกันสแกนซ้อน (`_SCAN_LOCK`) อยู่ในหน่วยความจำของ process และ SQLite ไม่ชอบการเขียนพร้อมกันหลาย process
- **ยังไม่รองรับ Postgres** — `DATABASE_URL` รับค่าอื่นได้ แต่ migration ยังใช้ไวยากรณ์แบบ SQLite (เช่นเทียบ `is_demo = 1`) ถ้าจะย้ายไป Postgres ต้องแก้ `backend/app/core/database.py` ก่อน
- **API ไม่มีระบบยืนยันตัวตน** — ใครที่รู้ URL ก็ยิง `POST /api/scan` หรือแก้ pipeline ได้ ถ้าเปิดสาธารณะควรใส่ auth หรือจำกัด IP ที่ชั้น host ก่อน
- **`POST /api/scan` ตอบ 202 ทันที** ไม่รอจนสแกนจบ (รอบเต็มใช้ 5–25 นาที นานกว่าเพดาน proxy ทุกตัว) หน้าเว็บจะตามผลจาก `GET /api/scan/logs` เอง
- **รอบสแกนเต็มอาจรันไม่จบบน free instance** — ใช้ `SCAN_SOURCE_TYPES` จำกัดแหล่งประกาศปัจจุบัน และแยกการกวาดประวัติ e-GP เป็นงานที่สั่งเพิ่มเติม ระยะเวลาขึ้นกับต้นทางและทรัพยากรของ host
