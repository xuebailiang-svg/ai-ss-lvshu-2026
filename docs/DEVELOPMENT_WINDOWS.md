# Windows 11 寮€鍙戠幆澧冭鏄?
鏈枃妗ｇ敤浜庡湪 Windows 11 涓婅繍琛屽悓涓€浠戒唬鐮佽繘琛屾湰鍦板紑鍙戣皟璇曘€傜敓浜х幆澧冧粛鐒舵槸 Ubuntu 22.04 + nginx + systemd + PostgreSQL锛沇indows 鍙綔涓哄紑鍙戠幆澧冿紝涓嶇淮鎶ょ浜屽浠ｇ爜銆?
## 1. 鐩爣鐜

鎺ㄨ崘鐗堟湰锛?
| 缁勪欢 | 寤鸿鐗堟湰 | 璇存槑 |
| --- | --- | --- |
| Windows | Windows 11 | 鏈湴寮€鍙戣皟璇?|
| Python | 3.11 / 3.12 / 3.13 | FastAPI backend; current pinned dependencies do not support Python 3.14 |
| Node.js | 20+ | React / Vite 鍓嶇 |
| npm | Node.js 鑷甫 | 鍓嶇渚濊禆绠＄悊 |
| PostgreSQL | 15+ | 鏈湴鏁版嵁搴?|
| Git | 2.40+ | 浠ｇ爜绠＄悊 |

妫€鏌ュ懡浠わ細

```powershell
python --version
node --version
npm --version
psql --version
git --version
```

濡傛灉 `python` 涓嶅彲鐢紝涔熷彲浠ヤ娇鐢?Windows Python Launcher锛?
```powershell
py -3 --version
```

## 2. 瀹夎鍩虹杞欢

### Python

浠庡畼缃戝畨瑁?Python 3.11 / 3.12 / 3.13锛?
```text
https://www.python.org/downloads/windows/
```

瀹夎鏃跺嬀閫夛細

```text
Add python.exe to PATH
```

### Node.js

浠庡畼缃戝畨瑁?Node.js 20+ LTS锛?
```text
https://nodejs.org/
```

### PostgreSQL

浠庡畼缃戝畨瑁?PostgreSQL 15+锛?
```text
https://www.postgresql.org/download/windows/
```

瀹夎鍚庣‘璁?`psql` 鍦?PATH 涓€傚鏋滄病鏈夛紝闇€瑕佹妸 PostgreSQL 鐨?`bin` 鐩綍鍔犲叆 PATH锛屼緥濡傦細

```text
C:\Program Files\PostgreSQL\16\bin
```

## 3. 鍒涘缓鏈湴鏁版嵁搴?
浠ヤ笅鍛戒护绀轰緥浣跨敤 PostgreSQL 榛樿绠＄悊鍛樼敤鎴?`postgres`銆傚鏋滀綘鐨勫畨瑁呬娇鐢ㄤ簡涓嶅悓鐢ㄦ埛鍚嶏紝璇锋浛鎹€?
```powershell
psql -U postgres
```

杩涘叆 psql 鍚庢墽琛岋細

```sql
CREATE USER site_selection WITH PASSWORD 'change_this_strong_password';
CREATE DATABASE site_selection OWNER site_selection;
\q
```

鏈湴寮€鍙戦粯璁ゆ暟鎹簱杩炴帴绀轰緥锛?
```env
DATABASE_URL=postgresql+psycopg://site_selection:change_this_strong_password@localhost:5432/site_selection
```

## 4. 鍒濆鍖?Windows 寮€鍙戠幆澧?
鍦ㄩ」鐩牴鐩綍鎵ц锛?
```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/install_windows.ps1
```

鑴氭湰浼氬畬鎴愶細

- 妫€鏌?`python` / `node` / `npm` / `psql`
- 濡傛灉 `.env` 涓嶅瓨鍦紝浠?`.env.example` 鍒涘缓
- 鍒涘缓 `backend/.venv`
- 瀹夎鍚庣渚濊禆
- 瀹夎鍓嶇渚濊禆
- 鍒涘缓鏈湴 `data/site_feedback.json`
- 鍒涘缓鏈湴 `data/agent_traces.json`
- 鍒涘缓 `frontend/public/runtime-config.json`

娉ㄦ剰锛?
```text
frontend/public/runtime-config.json
```

鏄湰鍦板紑鍙戣繍琛屾椂閰嶇疆锛屽凡缁忚 `.gitignore` 蹇界暐锛屼笉瑕佹彁浜ょ湡瀹?Key銆?
## 5. 閰嶇疆鐜鍙橀噺

缂栬緫椤圭洰鏍圭洰褰?`.env`锛?
```powershell
notepad .env
```

鍏抽敭閰嶇疆锛?
```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://site_selection:change_this_strong_password@localhost:5432/site_selection

AMAP_WEB_SERVICE_KEY=
AMAP_MOCK=false

VITE_AMAP_JS_KEY=
VITE_AMAP_SECURITY_JS_CODE=

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=true

SITE_FEEDBACK_STORE_PATH=data/site_feedback.json
AGENT_TRACE_STORE_PATH=data/agent_traces.json
FRONTEND_RUNTIME_CONFIG_PATH=frontend/public/runtime-config.json
```

璇存槑锛?
- `AMAP_WEB_SERVICE_KEY` 鏄悗绔珮寰?Web 鏈嶅姟 Key锛屼笉鍏佽鍐欏叆鍓嶇銆?- `VITE_AMAP_JS_KEY` 鍜?`VITE_AMAP_SECURITY_JS_CODE` 鏄祻瑙堝櫒鍦板浘浣跨敤鐨勫叕寮€閰嶇疆銆?- `DEEPSEEK_API_KEY` 鍙湪鍚庣浣跨敤锛屼笉鍏佽杩涘叆鍓嶇銆?- 娌℃湁 DeepSeek Key 鏃讹紝鍚庣搴旇姝ｅ父鍚姩锛汚I 鎶ュ憡/鑱婂ぉ鎺ュ彛浼氳繑鍥炴槑纭彁绀恒€?
濡傛灉淇敼浜?`.env` 涓殑鍓嶇鍦板浘 Key锛岄渶瑕佸悓姝ユ洿鏂帮細

```text
frontend/public/runtime-config.json
```

鎴栧垹闄よ鏂囦欢鍚庨噸鏂拌繍琛岋細

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start_frontend.ps1
```

## 6. 鍚姩鍚庣

鎵撳紑绗竴涓?PowerShell 绐楀彛锛屽湪椤圭洰鏍圭洰褰曟墽琛岋細

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start_backend.ps1
```

榛樿鍚姩锛?
```text
http://127.0.0.1:8000
```

鍋ュ悍妫€鏌ワ細

```powershell
curl http://127.0.0.1:8000/api/system/health
```

鏈熸湜杩斿洖锛?
```json
{
  "status": "ok",
  "warnings": []
}
```

## 7. 鍚姩鍓嶇

鎵撳紑绗簩涓?PowerShell 绐楀彛锛屽湪椤圭洰鏍圭洰褰曟墽琛岋細

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start_frontend.ps1
```

榛樿鍚姩锛?
```text
http://localhost:5173
```

Vite 浼氭妸 `/api` 浠ｇ悊鍒帮細

```text
http://localhost:8000
```

鍥犳娴忚鍣ㄥ彧闇€瑕佽闂細

```text
http://localhost:5173
```

## 8. 娴忚鍣ㄨ皟璇曠洰鏍?
Windows 寮€鍙戝惎鍔ㄥ悗锛屽簲鑳藉湪娴忚鍣ㄧ湅鍒帮細

- 椤圭洰鍒楄〃
- 椤圭洰璇︽儏
- 楂樺痉鏁版嵁閲囬泦
- 浜哄伐琛ュ厖
- 璇勫垎
- AI 鎶ュ憡
- AI 鑱婂ぉ

淇敼鍓嶇浠ｇ爜鍚庯紝Vite 浼氳嚜鍔ㄥ埛鏂伴〉闈€?
## 9. Codex 璋冭瘯寤鸿

Windows 鏈湴寮€鍙戞ā寮忎笅锛孋odex 鍙互锛?
- 鍚姩鍚庣鏈嶅姟
- 鍚姩鍓嶇 Vite 鏈嶅姟
- 浣跨敤 Playwright 鎵撳紑 `http://localhost:5173`
- 鏌ョ湅 Console 閿欒
- 鏌ョ湅 Network 璇锋眰
- 杩愯鍚庣娴嬭瘯
- 杩愯鍓嶇娴嬭瘯鍜屾瀯寤?
甯哥敤鍛戒护锛?
```powershell
# 鍚庣娴嬭瘯
cd backend
pytest

# 鍓嶇娴嬭瘯
cd frontend
npm test -- --run
npm run build

# Playwright 娴忚鍣ㄦ祴璇?cd frontend
npx playwright install chromium
npx playwright test
```

## 10. Windows 鍜?Ubuntu 鐨勫叧绯?
Windows 涓?Ubuntu 浣跨敤鍚屼竴浠戒唬鐮併€?
鍖哄埆鍙湪杩愯鏂瑰紡鍜岄厤缃枃浠朵綅缃細

| 鐜 | 鍚庣閰嶇疆 | 鍓嶇 runtime 閰嶇疆 | 鍚姩鏂瑰紡 |
| --- | --- | --- | --- |
| Windows 寮€鍙?| `.env` | `frontend/public/runtime-config.json` | PowerShell + Vite |
| Ubuntu 鐢熶骇 | `/etc/esports-site-selection/backend.env` | `/etc/esports-site-selection/frontend-runtime.json` | systemd + nginx |

Ubuntu 鐢熶骇閮ㄧ讲涓嶅彈 Windows 鑴氭湰褰卞搷銆?
## 11. 甯歌闂

### 1. PowerShell 涓嶅厑璁告墽琛岃剼鏈?
浣跨敤锛?
```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start_backend.ps1
```

### 2. 鏁版嵁搴撹繛鎺ュけ璐?
妫€鏌ワ細

```powershell
psql -U site_selection -d site_selection -h localhost
```

纭 `.env` 涓細

```env
DATABASE_URL=postgresql+psycopg://site_selection:change_this_strong_password@localhost:5432/site_selection
```

### 3. 鍦板浘绌虹櫧

妫€鏌ワ細

```text
frontend/public/runtime-config.json
```

蹇呴』鍖呭惈锛?
```json
{
  "amapJsKey": "浣犵殑鍓嶇楂樺痉 JS Key",
  "amapSecurityJsCode": "浣犵殑楂樺痉 JS 瀹夊叏瀵嗛挜",
  "mapProvider": "amap"
}
```

鍚屾椂纭楂樺痉鎺у埗鍙板凡鍏佽鏈湴寮€鍙戝煙鍚嶏細

```text
http://localhost:5173
```

### 4. AI 鎶ュ憡鎴栬亰澶╀笉鍙敤

妫€鏌?`.env`锛?
```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

娌℃湁 Key 鏃讹紝绯荤粺搴旀甯稿惎鍔紝浣?AI 鎺ュ彛浼氭彁绀?Key 鏈厤缃€?
## Python 3.14 compatibility note

The current backend dependency set pins:

```text
psycopg[binary]==3.2.6
```

On Python 3.14 this can fail with:

```text
No matching distribution found for psycopg-binary==3.2.6
```

Use Python 3.11, 3.12 or 3.13 for Windows development. The Windows PowerShell scripts intentionally reject Python 3.14 so a failed dependency install cannot be reported as a successful deployment.
