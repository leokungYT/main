# LINE Rangers (com.linecorp.LGRGS) — บันทึกการแกะระบบผ่าน ADB

เก็บข้อมูลจากเครื่อง `127.0.0.1:16512` (LDPlayer/Nemu, Android 12, root ได้) วันที่ 2026-09-13
เวอร์ชันทรัพยากรในเครื่อง: sound 12.2.4 / event sound 12.3.1, Resource-Timestamp 1785811215000

## 1. แพ็กเกจ & สถาปัตยกรรม

| ส่วน | รายละเอียด |
|---|---|
| Package | `com.linecorp.LGRGS` (อีกตัวในเครื่อง `com.linecorp.LGATF`) |
| Activity หลัก | `com.linecorp.LGRGS.LineRangersAdr` |
| Engine | cocos2d-x (C++) — logic เกือบทั้งหมดอยู่ใน `libgame.so` (32 MB, arm64) |
| Build path | `/Users/ad03148361/jenkins_workspace/lgrgs/lgrgs-aos-REAL/...` |
| Platform SDK | LINE Game **Trident** 3.12.1.422 (`libtrident*.so`) — login / analytics / promotion / termview / marketing |
| ป้องกัน | **LIAPP v5.0.1.198** (Lockin Company) → `assets/LIAPP.ini`, `assets/.tzyxaxtyd.dex`, `libtzyxaxtyd.so`, โฟลเดอร์ obfuscate `files/.7a313957/` |
| Network stack | libcurl + OpenSSL + nghttp2 คอมไพล์รวมอยู่ใน `libgame.so` (รองรับ HTTP/2) |
| DB | `libsqlcipher.so` (zetetic android-database-sqlcipher) |
| Crash/log | Sentry `https://…@ly.my.sentry.io/394`, NELO (`NeloSendCacheManager`) |

## 2. API Server

```
release : https://rangers-api.line-apps.com
beta    : https://rangers-api.line-apps-beta.com
alpha   : https://rangers-api.line-apps-alpha.com
CDN     : http://cdn-lg.line-apps.com/...
          https://static-inhouse.line-apps-beta.com/inhouse/lgrangers/resources
terms   : https://game-terms.line.me
```

IP ตอนรันจริง = เน็ตบล็อก LINE `147.92.x.x` พอร์ต 443 และ `147.92.240.68:15508` (ซ็อกเก็ต push/GNF ของแพลตฟอร์ม)

REST เป็น JSON ล้วน โครงสร้าง response คือ `{"result":{...},"version":...}`

### กลุ่ม endpoint ที่แกะได้ (รวม 208 path)

- **ผู้เล่น**: `/player/name` `/player/setting` `/player/profile/images` `/player/upgrade/` `/player/upgrade/status` `/player/item/purchase` `/player/item/sell` `/player/terms/agree` `/player/gidName`
- **ตัวละคร/เกียร์**: `/player/units/lock` `/player/units/unlock` `/player/units/potential/main` `/player/units/ability/awake/ticket/get` `/player/units/equip/{attach,detach,switch,sell,lock,advance,advance/retry}`
- **กาชา**: `/gacha/info` `/gacha/history` `/gacha/group/reserve` → `/gacha/group/confirm` → (`/gacha/group/adPlay`)
- **ด่าน**: `/stage/main` `/stage/last` `/eventstage/main` `/eventstage/battle/enter` `/eventstage/rank/player` `/area/player/keyitem`
- **กิลด์**: `/guild/{create,search,list,attendance,check/name}` `/guild/raid/{main,ladder,guardians,expend,schedule,reward/list}` `/guildwar/{main,form/register,form/cancel,battle/enter,defencedeck,replay/list}`
- **PvP**: `/pvp/main` `/pvp/flag/list` `/pvp/change/flag` `/pvp/battle/guardianlist`
- **แล็บ**: `/laboratory` `/laboratory/production` `/laboratory/production/accept/all` `/laboratory/production/complete/all` `/laboratory/expedition` `/laboratory/fusion/` `/laboratory/secret/main`
- **อีเวนต์**: `/bingo/*` `/roulette/main` `/randomdice/main` `/starWish/*` `/tokenbox/main` `/puzzle/main` `/spaceTrain/*` `/labyrinth/*` `/advent/area/schedule` `/sally/gift/box/event/receive`
- **เควส/รางวัล**: `/dailyquest` `/mission/sevendays/list` `/mission/list/new/` `/giftbox/list` `/attendance/cbu` `/pass/main` `/pass/reward/history` `/package/personal/newly/exposed` `/package/reward/history`
- **เพื่อน**: `/friend/main` `/friend/help/multi` `/friend/mercenary` `/friend/search/gid` `/friend/search/lProfile/uid` `/friend/request/{send/uid,received,allow,deny,cancel}` `/friend/remove`
- **บัญชี**: `/account/delete` `/guestMigration/register` `/guestMigration/confirm` `/switchLoginMethod/prepare` `/switchLoginMethod/confirm`
- **อื่น ๆ**: `/ruby/balance` `/coin/purchase` `/new/resources/all` (manifest) `/notice/news` `/cgp/list` `/crosspromotion` `/blockchain/nft/*` `/tutorial/confirm/<STEP>`
- **ของเซิร์ฟทดสอบ** (มีในไบนารีแต่ใช้ได้เฉพาะ dev): `/test/user/reset` `/test/player/ruby/purchase` `/test/player/unit/deleteall` `/test/player/tutorial/reset` ฯลฯ คู่กับคลาส `ApiTestController`, `GameCheatingController`, `GoodsCheatingController`

### สคีมา response

ในไบนารีมี JSON ตัวอย่างฝังไว้เป็น fixture (บล็อกใหญ่สุด ~15 KB) เห็นฟิลด์จริงครบ

object `player`:
`uid, mid, userName, imageUrl, level, exp/maxExp, friendship, gachaMileage, hearts{innerFree,innerPaid,cpFree,outerFree,free,paid,total}, maxHeart, heartEnded, nextHeartMills, secondaryHearts{...}, coin{...}, gem, crystal{crystal1..3}, useTeamNo/usePvPTeamNo/useSecondTeamNo…, lastStageCode, rsn, season, guest, expBoostEndTime`

object `playerUnit`:
`invenId, grade, level, exp, attack/hp/defence, finalAttack/finalHp, attackType, attackRange, attackScope, attackSpeed, knockbacks, movingSpeed, abilityCode/abilityCode2, awakeAbilityGroup, awakeYn, criticalProbability, criticalRatio, avoidProbability, antiAvoidProb, flightYn, …`

## 3. ไฟล์ในเครื่อง

```
/data/data/com.linecorp.LGRGS/
  shared_prefs/
    _LINE_COCOS_PREF_KEY.xml    ← บัญชี: _ENC_LF_AC_KEY (เข้ารหัส), _LF_UT_KEY=GUEST,
                                   _DEVICE_UUID_KEY, USER_NATION_CODE, LANGUAGE_TYPE_SETTING_KEY
    Cocos2dxPrefsFile.xml       ← state ฝั่งไคลเอนต์ 293 คีย์
    trident.preferences.xml / pcvmspf.xml  ← โทเคนแพลตฟอร์ม LINE Game
  files/.res/
    base_res/res_base_hd.txt    ← manifest ทรัพยากร (JSON 4.4 MB, 6586 รายการ)
    preload/__lang_prop.ndb, __lang_tip.ndb, __loading_unit.eson
    ca.cer                      ← GlobalSign Root R3 (pin CA)
  files/.7a313957/              ← ไฟล์ของ LIAPP (มี .jar ชื่อเป็นอักษรอารบิก)
/sdcard/Android/data/com.linecorp.LGRGS/files/.res/   ← ทรัพยากรที่โหลดมา 4035 โฟลเดอร์
```

### คีย์ใน Cocos2dxPrefsFile ที่น่าสนใจ

- ค่ากลาง: `USER_GAME_ID`, `LRTKEY`, `userType=GUEST`, `USER_NATION_CODE`, `COMMON_UDK_AND_GRAPHIC_MODE=HD`, `LAST_RESOLUTION_KEY=RESOLUTION_HD`, `KEY_RESOURCE_STATUS`, timeout: `CONNECT_TIMEOUT_VALUE=30` / `READ_TIMEOUT_VALUE=40` / `RES_CONNECT_TIMEOUT_VALUE=15` / `RES_READ_TIMEOUT_VALUE=30`
- ต่อบัญชี: คีย์ลงท้ายด้วย MD5 32 ตัว (hash ของ user key) เช่น `HOME_LAST_TIMESTAMP<MD5>`, `LAST_TEAM_SEQ_KEY<MD5>`, `KEY_NEW_PERSONAL_PACKAGE_SEQ_LIST<MD5>`, `UDK_WEEKLY_FESTIVAL_CHECKED_SEQ_LIST<MD5>`, `bingoEventSeq<MD5>` — เครื่องนี้มีค้างอยู่ ~20 บัญชี
- ป๊อปอัป: `UDK_MAIN_POPUP_DONT_SHOW_TODAY_<seq>` / `UDK_MAIN_POPUP_DONT_SHOW_ALWAYS_<seq>` → ปิดป๊อปอัปได้จาก prefs ตรง ๆ โดยไม่ต้องกดจอ
- `UDK_SCD/SCM`, `UDK_SRD/SRM`, `UDK_SHD/SHM`, `UDK_ESCD/ESCM` … = ก้อน base64 เข้ารหัส + timestamp คู่กัน (config/notice ที่แคชไว้)

## 4. ตารางข้อมูลเกม (ส่วนที่มีค่าที่สุดสำหรับบอต)

manifest `res_base_hd.txt` มีรูปแบบ
`{"result":{"Resource-Timestamp":…,"resources":[{resourceId,resourceType,resourcePath,signature(md5),size,deleted}]}}`

รวม 6586 ไฟล์: `zip` 3869 (สไปรท์) / `ogg` 2577 (เสียง) / **`db` 130** / **`ndb` 10**

- **`.ndb` = SQLite ธรรมดา อ่านได้เลย** ✔
- **`.db` = เข้ารหัส (SQLCipher)** — เปิดตรง ๆ ไม่ได้ ยังไม่ได้คีย์

ตัวที่อ่านได้ทันที (ndb): `lang_unit` (11 MB), `lang_etc`, `lang_prop`, `lang_area`, `lang_equip`, `lang_guild`, `lang_tip`, `sound_metadata`, `special_area`

ตัวอย่าง `lang_unit.ndb`:

```sql
CREATE TABLE lang_unit(dataCode, language, msgType, msg)   -- 70,055 แถว
-- language: en, ja, ko, th, zh-Hant ; msgType: UNIT / SKILL / ABILITY
select msg from lang_unit where dataCode='u1617e-ka_nm' and language='th';
```

**รูปแบบรหัสตัวละคร**: `u<id><เกรด>-<tag>` โดย `e` = ปกติ, `h` = ร่างที่สอง, `u` = Ultimate
เช่น `u1617e-ka` = Kafka, `u1617h-ka` = First Division Kafka, `u1617u-ka` = Third Division Kafka, `u1618e-ka` = Kaiju No.8 Kafka
→ ตรงกับชื่อที่ใช้ใน `configmain.json` (`Kafka+` / `KafkaU+` / `kikoru+` / `kikoruU+`)

ชื่อ DB ที่เข้ารหัส (บางส่วน): `unit`, `skill`, `ability`, `game_item`, `game_item_equip`, `unit_eqip_attr`, `unit_evln_mtrl`, `unit_reinforce_rate`, `mini_gacha_info`, `stage`, `stage_ai`, `stage_productline`, `event_stage*`, `guild_raid_stage*`, `labyrinth_*`, `space_train_*`, `expedition_*`, `eqip_*`, `tlnt*`, `roulette_*`, `random_dice_*`, `machine_upgrade`, `level_figure_info`, `player_unit_reinforce_detail`, `rangers_pass_info`

## 5. โครงสร้างโค้ดเกม (จาก RTTI ใน libgame.so — ชื่อคลาสไม่ถูก strip)

พบ ~1810 คลาส แบ่งได้เป็น

- **Controller 125 ตัว** = 1 หน้าจอ/1 ฟีเจอร์: `GameSplashController`, `HomeController`, `GachaController`, `GachaPlayController`, `GearMainController`, `GearEnhanceController`, `GearSwitchController`, `GearAdvanceResultController`, `EvolveController`, `UnitPotentialUpController`, `UpgradeMainController`, `BattleController`, `PvpMainController`, `GuildWarMainController`, `LabyrinthMainController`, `SpaceTrainMainController`, `RangersPassMainController`, `ExchangeController`, `TreasureController`, `ResourceUpdateController` …
- **Manager 75 ตัว**: `PlayerManager`, `UnitManager`, `GearManager`, `ShopManager`, `AutoBattleManager`, `RepeatBattleManager`, `StageAutoPlayManager`, `BattleManager` / `BattleResultManager` / `BattleLogManager`, `ReplayLogManager`, `MultiNetworkManager`, `ResourceManager`, `DBLoadManager`, `SceneHistoryManager`, `RewardBadgeManager`, `ShopBadgeManager`
- **DB wrapper 132 ตัว**: `UnitDB`, `SkillDB`, `AbilityDB`, `GearDB`, `GearAttrDB`, `GearRandomOptionDB`, `StageDB`, `StageAiDB`, `LangUnitDB` … (แมป 1:1 กับไฟล์ .db/.ndb ข้างบน)
- **Network**: `NetworkClient`, `MultiNetworkManager`, `ResponseChecker` / `ResponseCheckerObserver`, `LCResponseDelegate`, `GPGNFNetwork` (ซ็อกเก็ตแพลตฟอร์ม), `ExchangeApiManager`

จุดที่ตรงกับงานบอต: `AutoBattleManager` / `RepeatBattleManager` / `StageAutoPlayManager` = ระบบออโต้ในตัวเกม, `GearSwitchController` / `GearAdvanceResultController` = ระบบสลับ/อัปเกียร์ที่ `ranger-gear.py` ไปกดอยู่

## 6. ข้อจำกัด / สิ่งที่ยังไม่ได้

1. **คีย์ SQLCipher ของ `.db`** — `libgame.so` ไม่มี sqlite อยู่ในตัวเอง (import มีแค่ libtrident / GLES / log / z / OpenSLES / c / m / dl) แปลว่าเปิด DB ผ่านฝั่ง Java (`net.zetetic.database.sqlcipher` อยู่ใน classes5.dex) คลาสที่เรียกถูก obfuscate และมี LIAPP ป้องกัน ต้อง hook runtime (frida หรือ dump จาก `/proc/<pid>/mem`) ถึงจะได้คีย์
2. **auth header ของ REST** — ไม่มีสตริงชื่อ header ชัดเจนในไบนารี ใช้ Cookie ร่วมกับ `LRTKEY` จาก Trident การยืนยันต้อง MITM ซึ่งแอป pin `ca.cer` (GlobalSign R3) ไว้ + LIAPP ตรวจ proxy/root
3. โปรโตคอลพอร์ต 15508 ยังไม่ได้แกะ (อยู่ใน `libtrident.so`)

## 7. ใช้ประโยชน์ได้ทันทีกับบอต

- ดึง `lang_unit.ndb` มาทำ **ตารางชื่อตัวละคร → รหัส** (ครบทุกภาษา) แทนการเดา/OCR ชื่อ และแยกเกรด e/h/u ได้แม่นยำ (ตรงกับ `HERO_MAPPING`, `Hero_low` ใน `configmain.json`)
- `lang_prop.ndb` / `lang_etc.ndb` = ข้อความ UI ทั้งหมด → ทำ dictionary ให้ Tesseract อ่านข้อความป๊อปอัปแม่นขึ้น
- `UDK_MAIN_POPUP_DONT_SHOW_TODAY_<seq>` ใน `Cocos2dxPrefsFile.xml` → เซ็ตล่วงหน้าเพื่อกันป๊อปอัป แทนการจับภาพแล้วกดปิด (ตรงกับโค้ด popup ใน `login.py` / `ranger-gear.py` / `rangerplus.py`)
- `res_base_hd.txt` บอก signature + size ของทุกไฟล์ → เช็กได้ว่าทรัพยากรโหลดครบก่อนเริ่มรัน แทนการรอ black screen timeout

## 8. คำสั่งที่ใช้เก็บข้อมูล (ทำซ้ำได้)

```bash
ADB="./adb/adb.exe -s 127.0.0.1:16512"
$ADB shell "su -c 'cp -r /data/data/com.linecorp.LGRGS/shared_prefs /sdcard/lgr_prefs'"
$ADB pull /sdcard/lgr_prefs
$ADB shell "su -c 'cp /data/data/com.linecorp.LGRGS/files/.res/base_res/res_base_hd.txt /sdcard/'"
$ADB pull /sdcard/Android/data/com.linecorp.LGRGS/files/.res/lang_unit/lang_unit.ndb
$ADB pull "/data/app/~~.../com.linecorp.LGRGS-.../split_config.arm64_v8a.apk"   # libgame.so อยู่ในนี้
```

---

## 9. Auth / การดัก flow / เป้าหมาย "ล็อกอิน+รับของ ผ่าน API" (อัปเดตรอบ 2)

### โมเดล auth
- บัญชีเป็น **GUEST** login ผ่าน **Trident** (LINE Game platform) ไม่ใช่ REST เส้นเดียว
- โทเคนเก็บใน `shared_prefs/trident.preferences.xml` แต่ **เข้ารหัสทั้งหมด** (base64+AES ผูกเครื่อง ถอดด้วย `libline-sdk-encryption.so`):
  `com.linecorp.trident.accesstoken` / `.refreshtoken` / `.providertoken` / `.userkey` / `.uuid`
  มี `.accesstoken.expiretime` / `.refreshtoken.expiretime` → **อายุสั้น** ต้อง refresh ผ่าน handshake
- REST ที่ `rangers-api.line-apps.com` ใช้ session ที่ออกจาก handshake นี้ (Cookie/LRTKEY) — ไม่มี UID→เข้าได้

### SSL pinning (ยืนยันจาก libgame.so)
libcurl ใช้ **CURLOPT_PINNEDPUBLICKEY** ปักหมุด public key ของเซิร์ฟเวอร์ 2 ค่า:
```
sha256//BUdSKtKLHmP1k5INP5VXHEtO71jjIMbSTvP6H5vXH2w=
sha256//HtbmQiaLc4M5JnCyEF6FRiQjq+fChdr3Hw1MrkW5lzc=
```
error string: `SSL: public key does not match pinned public key!`
→ ยัด CA/แก้ `ca.cer`/MITM proxy = โดนปฏิเสธ

### กำแพงบนอีมูฯ ตัวนี้ (MuMu x86_64 + native-bridge) — ทดสอบครบแล้ว
| วิธี | ผล | เหตุผล |
|---|---|---|
| MITM (mitmproxy+CA) | ❌ | โดน pinned public key |
| frida hook native (SSL_read/DB key) | ❌ | frida เป็น x86_64 มองไม่เห็น `libgame.so`/`libsqlcipher.so` ที่เป็น **arm64** รันผ่าน native-bridge (nb) |
| memory scrape /proc/pid/mem | ⚠️ | reader ทำงานถูก (เจอ `rangers-api` ใน rodata) แต่ request/response/token **ไม่ค้างเป็น plaintext** ใน heap (parse แล้ว free / เป็น binary / อยู่โซน translated) |
| patch+repack libgame | ❌ | ติด LIAPP integrity check |

**สรุป: บนอีมูฯ x86 ตัวนี้ ดัก flow จริงเพื่อ "แยกเส้น API มายิงเอง" ไม่ได้**

### ทางที่ได้ครบ (ต้องเปลี่ยนสภาพแวดล้อม)
รันบัญชีเดียวบนเครื่อง **arm64 จริง** (มือถือ root / emulator ARM แท้: Genymotion ARM, Android Studio arm64, Waydroid arm) → `frida-server-arm64` → hook `SSL_read`/`SSL_write` ใน libgame **ทะลุ pin** (อ่านหลังถอดรหัส) เห็น request+response+token+ลายเซ็นครบ
สคริปต์พร้อมใช้: [`LGR-frida-ssl-capture.js`](LGR-frida-ssl-capture.js)
จุดชี้เป็นชี้ตายหลังดักได้: **request มี HMAC/signature ต่อ nonce ไหม** — ถ้ามี ต้องเลียนแบบการเซ็น (ยาก); ถ้าไม่มี ยิงเองด้วย token สดได้

### สิ่งที่ทำได้ทันทีบนอีมูฯ นี้ (ไม่ต้อง bypass อะไร)
**ตรวจ "เข้าเกม/โหลด home สำเร็จ" แทน OCR/image-match** ผ่าน root อ่าน pref:
- `Cocos2dxPrefsFile.xml` → คีย์ `HOME_LAST_TIMESTAMP<MD5>` = **epoch-ms ปกติ** (เช่น `1789306663255`) อัปเดตเมื่อ home ของบัญชีนั้นโหลดเสร็จ
- วิธีใช้: เปิดแอป → poll ค่า **max** ของทุก `HOME_LAST_TIMESTAMP*` เทียบ `now`; ถ้าห่าง < N วินาที = เข้าเกมแล้ว
- `USER_GAME_ID` = บัญชีที่ล็อกอินอยู่ตอนนี้ (เปลี่ยนตามบัญชี), timestamp เป็น ms ตรง อ่านง่าย
- **แต่ "รับของ" ยังต้องกดจอเหมือนเดิม** (เส้น API รับของยิงเองไม่ได้บนเครื่องนี้)

---

## 10. สรุปการทดสอบ frida + คำตอบสุดท้ายเรื่อง "ยิง API เอง" (อัปเดตรอบ 3)

### ทดสอบด้วย frida จนสุดทางแล้ว
ติดตั้ง frida-server-x86_64 บนอีมูฯ (MuMu native-bridge). ผลลัพธ์:

| สิ่งที่ลอง | ผล | สรุป |
|---|---|---|
| `frida.enumerateModules()` | เห็นแต่ libssl/libcrypto **ของระบบ (x86_64)** | ❌ ไม่เห็น libgame.so/libsqlcipher.so (arm64) |
| hook `SSL_read/SSL_write`, `sqlite3_key` | `not a function` | ❌ native arm64 แตะไม่ได้ |
| attach ธรรมดา → create_script | timeout ซ้ำ | LIAPP arm anti-tamper แล้วขวาง inject |
| **spawn-gating** (`spawn`+`attach`+`load`+`resume`) | ✅ **ผ่าน LIAPP** | Java hook ทำงานได้เต็ม |
| hook `TridentNative` (Java) | มีแต่ utility (getAdjustId/getAndroidId…) | ❌ ไม่มี getUserKey/getAppSecret (auth เป็น C++ ล้วน) |
| hook `HttpURLConnection` / `URL.openConnection` | ไม่ทริก | handshake ไม่ผ่าน java.net |
| hook `okhttp3.RealCall.execute` + `LGNetworkModule.NetworkTask` (กด giftbox/news/shop/quest/mission) | **ไม่ทริกเลย** | ❌ **game API ไม่ได้วิ่งผ่าน Java** — เป็น native curl ล้วน |
| memory scrape token/request | reader ทำงานถูก แต่ไม่เจอ (ค่า free เร็ว/binary) | ❌ |

**บทสรุปเด็ดขาด:** traffic ของ rangers-api ทั้งหมดอยู่ใน **native curl (arm64)** ที่ static-link BoringSSL เอง — บนอีมูฯ x86 (native-bridge) **ดักไม่ได้ทุกวิธี** ชั้น Java (okhttp3/LGNetworkModule) โหลดไว้แต่เกมไม่ใช้ยิง API เกม

### ของที่ได้จากรอบนี้ (มีค่า)
1. **auth scheme ครบ** (จาก static analysis libgame.so) — header-based ไม่มีลายเซ็นต่อ body:
   `X-LINEGAME-APPID: LGRGS` / `-APPSECRET` / `-USERKEY` / `-TIMESTAMP` / `-MCC` / `-MNC` + `Cookie: <name>=<val>; udid=<uuid>;`
   ค่า USERKEY/APPSECRET มาจาก `linecorp::trident::AuthManager::getUserKey()` (native, libtrident)
2. **spawn-gating ผ่าน LIAPP v5** — เทคนิคนี้ใช้ได้ (พิสูจน์แล้ว) จำเป็นต้อง spawn ไม่ใช่ attach
3. **API config map** ฝังในไบนารี (short-code → path): `home=/home`, `ste=/stage/enter/%s`, `pbe=/pvp/battle/enter/%s`, `gre=/guild/raid/battle/enter/%s?force=%s` ฯลฯ

### ทางที่ "คนอื่นทำได้" ใช้จริง — และเราต้องทำแบบไหน
capture ต้องทำบน **arm64 แท้ครั้งเดียว** แล้ว bot ที่ได้รันบน farm x86 ได้ (bot = Python ยิง HTTPS ธรรมดา ไม่ต้อง arm64):

- **ทางหลัก:** มือถือ Android root (arm64) / emulator ARM (Corellium, หรือ AVD arm64 บนเครื่อง Apple Silicon) → frida-server-arm64 + **spawn-gating** + [`LGR-frida-ssl-capture.js`](LGR-frida-ssl-capture.js) hook `SSL_read/SSL_write` ใน libgame → เห็น request+response+token ครบ ทะลุ pin
- **ทางเลี่ยง:** หา **APK เวอร์ชันเก่า** (ก่อนใส่ pinning/LIAPP) ลงบน x86 → mitmproxy ธรรมดาดักได้ทันที เรียนรู้ header + auth scheme (server เดิม) — เสี่ยงเรื่อง auth เก่า/ใหม่ต่างกัน แต่เร็วสุดบนเครื่องที่มี

หลัง capture ได้ 1 flow: ถ้าไม่มี HMAC ต่อ request (ตามที่คาด) → เขียน Python client `ล็อกอิน(ยืม token)+รับของ` ได้จริง โดยดึง `X-LINEGAME-USERKEY/APPSECRET/Cookie` สดจากแอปที่รันอยู่

---

## 11. ✅ สำเร็จ: ยิง API เอง "ล็อกอิน + รับของ" ได้จริง (2026-09-14)

**MITM ทะลุได้** ด้วย reverse-proxy (ไม่ต้อง bypass pin — เกมยอมรับ cert ของ mitmproxy!):
- routing: hosts `rangers-api.line-apps.com → 127.0.0.1` (bind-mount) + `iptables REDIRECT 443→8443` + `adb reverse 8443` + `mitmdump --mode reverse:https://rangers-api.line-apps.com --listen-port 8443`
- เกมยิงผ่าน mitm ได้ decrypt เห็น request/response ครบ

### auth model จริง (ถอดจากทราฟฟิก)
```
GET/POST https://rangers-api.line-apps.com/v12.3/<path>
Cookie: udid=<device_uuid>; LF_AC=<session>            <-- auth มีแค่นี้ ไม่มีลายเซ็น/HMAC
(login ใช้ guestCookie=<credential ถาวร> เพิ่ม)
```
- **`LF_AC`** = session cookie ใช้เรียก endpoint ที่ต้อง auth ได้ตรง ๆ (ไม่ต้อง /login ซ้ำ)
  เซิร์ฟหมุนค่าใหม่ทาง `Set-Cookie: LF_AC=...` ทุก request -> เก็บค่าใหม่ไว้ใช้ต่อ
- **`guestCookie`** = ถอดจาก `_ENC_LF_AC_KEY` ในเครื่อง หมุนทุก login เก็บกลับแบบเข้ารหัส
- `udid` = `_DEVICE_UUID_KEY` (คงที่ต่อเครื่อง)
- ไม่มี `X-LINEGAME-APPSECRET/USERKEY/SIGNATURE` ในทราฟฟิกจริง (เดาผิดจาก static ก่อนหน้า — พวกนั้นคือ format string ที่มีแต่ไม่ได้ใช้เส้นนี้)

### endpoint รับของ (จาก libgame)
- `POST /v12.3/giftbox/gift/receive/all`  = รับของขวัญทั้งกล่อง
- `POST /v12.3/giftbox/{type}/receive/{giftSn}` = รับทีละชิ้น
- อื่น ๆ: `/mission/receive/reward/*`, `/dailyquest/receive/reward/*`, `/pass/receive/reward/*`,
  `/guild/raid/reward/receive/*`, `/roulette/accumulatedReward/receive/*`, `/tokenbox/reward/received` ฯลฯ

### พิสูจน์แล้ว (บัญชี guest 10a86152)
```
GET  /home              -> 200  badge GIFT=12
GET  /giftbox/list      -> 200  giftBox.gift.playerGifts[] (giftSn, receive:false)
POST /giftbox/gift/receive/all -> 200  (คืน player อัปเดต หัวใจ +)
ผล: unclaimed 12 -> 1  (รับไป 11 ชิ้น เช่น Feather+40, Leonard Soul+100, กาชาทิกเก็ต)
```

### ของที่ส่งมอบ
- [`lgr_api.py`](lgr_api.py) — client: `LGRClient(udid, lf_ac)` มี `.home()/.giftbox_list()/.receive_all_gifts()`
  + `collect_account(udid, lf_ac)` เช็กเข้าเกม+รับของทั้งหมด คืน lf_ac_next ให้เก็บใช้รอบหน้า
- [`capture_credential.py`](capture_credential.py) — mitmproxy addon จับ udid+LF_AC ต่อบัญชี -> creds.json (ทำครั้งเดียว/บัญชี)

### ข้อจำกัด/วิธีใช้จริง
- credential (LF_AC/guestCookie) **หมุน** -> ต้องเป็นเจ้าของคนเดียว: จับ credential ครั้งเดียวผ่าน MITM
  แล้วบัญชีนั้นใช้ API อย่างเดียว (อย่าเปิดเกมบัญชีเดิมพร้อมกัน เดี๋ยว credential ชนกัน)
- LF_AC หมดอายุได้ -> ถ้า 401 ให้ /login ด้วย guestCookie ใหม่ หรือ re-capture
- นี่คือ "ยิง API รับของโดยไม่ต้องเปิดเกม" ที่ต้องการ — เร็วมาก ทำขนานหลายบัญชีได้ (แค่วน creds.json)

## 12. ✅ ภารกิจ (mission) + กาชา — ยืนยันสดกับเซิร์ฟจริง 2026-09-16

ทดสอบกับบัญชีจริง `a0a604d8` (guest, Lv 3, ruby 121) ทุกอย่าง **200 หมด**

### ภารกิจ
```
GET  /v12.3/mission/list/new/                 -> dailyMissionTab / weeklyMissionTab / specialMissionTab
POST /v12.3/mission/receive/reward/<missionNo> -> รับ 1 ชิ้น (พิสูจน์: 3688 -> 200, ค้างเหลือ 1 -> 0)
```
- ชิ้นที่รับได้ = `missionComplete: true` และ `receiveReward: false`
- **daily/weekly รายชิ้นไม่มี `missionNo`** -> รับทีละอันไม่ได้ (ที่รับได้คือ specialMissionTab)
- ⚠️ **ยิง `/mission/list/new/` ซ้ำติด ๆ กันได้ 400** -> ดึงครั้งเดียวแล้วส่งต่อ อย่าเรียกซ้ำ
- `/mission/sevendays/list` **มีจริง** แต่คืน `errorCode 120900` กับบัญชีทั่วไป = อีเวนต์เฉพาะช่วง/กลุ่ม
- เครื่องมือ: `seven_days.py` (`--list` ดูเฉย ๆ / `--dump <id>` พ่น JSON ดิบ) , `seven-days.bat` ,
  `GET /api/missions?id=<key>&claim=0` ใน `web_app.py`

### กาชา — ยิงผ่าน API ได้จริง (ครั้งแรกที่พิสูจน์)
```
GET  /gacha/info                 -> gachaGroupResponseList[].gachaGroup.gachaGroupInfos[]
POST /gacha/group/reserve  {groupId,gachaId,gachaIndex} -> reserveSeq
POST /gacha/group/confirm  <ทั้งก้อน result ของ reserve> -> gachaResults[].rewards[].rewardUnit.unitCode
```
พิสูจน์: `grp_gacha_1 / gacha_grp_1` (10 ruby) -> ได้ `u2030e-jessica` , `usedRubyBalance.total=10`
- กาชาที่เปิดให้บัญชี Lv 3: `grp_gacha_1` 10 ruby/ครั้ง, `g_grp_tuto_pity1~3` 40-100 ruby,
  `grp_gacha_15` 50 ruby (ลดวันละครั้งเหลือ 30), 6 ใบ 300 ruby, ตั๋วอีเวนต์ `grp_gacha_40`
- **ไม่ต้องผ่าน tutorial step ใด ๆ** — บัญชีที่ผ่าน onboarding มาแล้วยิงได้เลย

### ทริคหา endpoint (ใช้ซ้ำได้)
เซิร์ฟแยก 2 แบบชัดเจน -> ใช้ id ปลอมยิงหา path ได้โดยไม่กระทบบัญชี
- path **ไม่มีจริง** -> `404` + `errorMessage` echo path นั้นกลับมา
- path **มีจริง** แต่ข้อมูลผิด -> `400` + `errorCode` ของเกม (เช่น 108101)

### creds.json อยู่ 2 ที่
root ว่าง (0 บัญชี) แต่ `api/creds.json` มี 414 บัญชี -> `lgr_api._pick_creds_file()`
เลือกไฟล์ที่ "มีข้อมูล" ให้อัตโนมัติแล้ว แต่ควรรวมให้เหลือไฟล์เดียวจริง ๆ

## 13. กาชาผ่านเว็บ + รีโรลเลือกตัว — 2026-09-16/17
- `web_app.py` เพิ่ม: `GET /api/gacha/info?id=<key>` (ตู้ที่ยิงได้+ruby/ตั๋ว) ,
  `GET /api/gacha/pull?id=<key>&group=&gacha=&index=&targets=&max=` (สุ่ม/รีโรล)
- หน้าเว็บ: ปุ่ม 🎲 ต่อแถว -> modal เลือกตู้ + ใช้ "ตัวที่เลือกไว้ (SELT)" เป็นเป้า -> รีโรลจนติด/หมด budget เห็นผลสด
- CLI: `gacha_reroll.py <id> --list | --group .. --gacha .. --index .. [--target ..]* [--max N] [--n N]`
- พิสูจน์: `grp_gacha_1/gacha_grp_1` (10 ruby) ยิงผ่านเว็บ+CLI ได้ตัวจริง, ruby ลดจริง
- ⚠️ `grp_gacha_1` เป็นตู้ tutorial/newbie (pool ล็อกผล) -> รีโรลจริงใช้ตู้ปกติ (ดู --list)

### creds.json เคยมี 2 พูลตีกัน (แก้แล้ว)
- root `creds.json` = ที่ capture_auto เขียน (ผ่าน creds.part<port>.json) ; `api/creds.json` = พูล API (414)
- รวมเป็นไฟล์เดียว 419 บัญชี เขียนตรงกันทั้ง root+api แล้ว
- `lgr_api._pick_creds_file()` = เลือกไฟล์ที่ "บัญชีเยอะกว่า" ; `save_creds()` = กันเขียน dict ว่างทับ
