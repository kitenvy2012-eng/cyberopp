# Deploy: Netlify (dashboard) + container host (backend)

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
2. Render อ่าน `render.yaml` เอง แล้วสร้าง service พร้อม disk 5 GB ที่ `/data`
3. รอจน health check ที่ `/api/health` เขียว แล้วจดโดเมนไว้ เช่น `https://cyberwatch-api.onrender.com`

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
| `BACKFILL_ON_EMPTY` | `true` เพื่อให้เติมข้อมูลเองตอนบูตครั้งแรก (`render.yaml` ตั้งไว้แล้ว) | – |
| `BACKFILL_YEARS_BACK` | จำนวนปีงบที่กวาดตอนเติมครั้งแรก (default `12`) | – |
| `DATA_GO_TH_API_KEY` | key จาก <https://opend.data.go.th/register_api> | – |

> **`/data` ต้องเป็น volume จริง** ถ้าไม่ mount ฐานข้อมูลจะอยู่ในคอนเทนเนอร์และหายทุกครั้งที่ redeploy

### เติมข้อมูลครั้งแรก

image ไม่ได้ใส่ไฟล์ `.db` มาด้วย (อยู่ใน `.dockerignore`) ฐานใหม่จึงว่างเปล่า เลือกทางใดทางหนึ่ง:

**ก. ปล่อยให้เติมเอง** (ค่าเริ่มต้นของ `render.yaml` — ไม่ต้องทำอะไรเลย)

เมื่อ `BACKFILL_ON_EMPTY=true` แอปจะตรวจตอนบูตว่าฐานว่างหรือไม่ ถ้าว่างจะกวาดประวัติ e-GP ให้เองแบบ **background** — `/api/health` ตอบทันทีตั้งแต่วินาทีแรก health check ของ host จึงไม่รอ (ทดสอบแล้ว: บูตจากฐานว่าง → health ตอบใน 0 วินาที → ได้ข้อมูลครบใน ~1 นาที)

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
- **ใช้ worker เดียวเท่านั้น** — `Dockerfile` ตั้ง `--workers 1` ไว้ เพราะตัวล็อกกันสแกนซ้อน (`_SCAN_LOCK`) อยู่ในหน่วยความจำของ process และ SQLite ไม่ชอบการเขียนพร้อมกันหลาย process
- **ยังไม่รองรับ Postgres** — `DATABASE_URL` รับค่าอื่นได้ แต่ migration ยังใช้ไวยากรณ์แบบ SQLite (เช่นเทียบ `is_demo = 1`) ถ้าจะย้ายไป Postgres ต้องแก้ `backend/app/core/database.py` ก่อน
- **API ไม่มีระบบยืนยันตัวตน** — ใครที่รู้ URL ก็ยิง `POST /api/scan` หรือแก้ pipeline ได้ ถ้าเปิดสาธารณะควรใส่ auth หรือจำกัด IP ที่ชั้น host ก่อน
- **`POST /api/scan` ใช้เวลาหลายนาที** — รอบสแกนเต็มวัดได้ 5–25 นาที ซึ่งนานกว่าเพดานของ proxy ทุกตัว ปุ่ม "สแกนทันที" บนหน้าเว็บจึงมักขึ้น timeout ทั้งที่งานฝั่ง backend ยังทำต่อจนจบ ให้ดูผลจริงที่ `GET /api/scan/logs`
