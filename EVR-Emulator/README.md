# EVR Emulator — Entorno de virtualización Android · "Elisandro"

Plataforma de virtualización Android para QA y compatibilidad de aplicaciones.
Motor QEMU (WHPX en Windows, KVM en Linux, HVF en macOS) con guest
Android-x86/BlissOS, puente ADB en Node.js y consola web con pantalla en vivo.

> **Estado:** Fases 1–4 operativas. El middleware, la consola y los scripts de
> VM funcionan en Windows, Linux y macOS. Ver *Roadmap* para lo que queda.

## Arquitectura (capas)

| Capa | Componente | Estado |
|------|------------|--------|
| 1 | Motor de virtualización — QEMU + WHPX/KVM/HVF, guest Android-x86/BlissOS, GPU (VirGL) | ✔ `launch-vm.ps1` · `launch-vm.sh` |
| 2 | Imagen Android — GApps para Play Store, patrón base+overlay para formateo | ✔ `vm-format.ps1` · `vm-format.sh` |
| 3 | Middleware — API REST + WebSocket de control + ADB + control de VM | ✔ `middleware/` |
| 3b | Streaming — canal `/ws/video`: el servidor empuja los fotogramas del guest | ✔ fotogramas PNG · H265 pendiente |
| 4 | Consola "Elisandro" — pantalla en vivo, clic/arrastre/teclado, agent switcher, apps, formateo | ✔ `frontend/` |

## Requisitos

- **Windows 10/11 x64** (objetivo principal) con CPU VT-x/AMD-V + SLAT (EPT/NPT), o
  **Linux con KVM** / **macOS con HVF** para desarrollo y QA.
- ≥ 8 GB RAM
- Node.js ≥ 18
- QEMU (solo para levantar la VM; el middleware y la consola no lo necesitan)

## Puesta en marcha

### Windows — un solo comando

```powershell
# deja el .iso de BlissOS-GApps en .\images\  y ejecuta:
powershell -ExecutionPolicy Bypass -File .\scripts\quickstart.ps1
```

`quickstart.ps1` hace: preflight → instala QEMU (winget) si falta → detecta el ISO →
la 1ª vez abre QEMU para **instalar** Android en `base.qcow2` → en la 2ª ejecución
**arranca** la VM + el middleware y abre la consola en http://127.0.0.1:5555.

**Requisito para el Play Store:** usa un ISO de **BlissOS que incluya GApps**
(build "GApps", Android 13/14 x86_64, desde https://blissos.org). Con eso el Play
Store viene instalado y solo hay que iniciar sesión con la cuenta Google.

### Linux / macOS — un solo comando

```bash
./scripts/quickstart.sh            # con VM (necesita QEMU y /dev/kvm)
./scripts/quickstart.sh --no-vm    # solo la consola, para un AVD o un móvil por USB
```

### Paso a paso (cualquier sistema)

```bash
# 1) Preflight + binarios (adb, scrcpy)
powershell -ExecutionPolicy Bypass -File .\elisandro-setup.ps1 -FetchBinaries   # Windows
./scripts/fetch-binaries.sh                                                     # Linux/macOS

# 2) Middleware
cd middleware
cp .env.example .env
npm install
npm run doctor     # diagnostica el entorno antes de arrancar
npm start
```

Consola web y API en **http://127.0.0.1:5555**.

`npm run doctor` comprueba Node, dependencias, `.env`, puerto libre, adb,
dispositivos conectados, resolución del guest, perfiles y consola web, y dice
exactamente qué falta cuando algo no está en su sitio.

## Cómo encuentra el dispositivo

El middleware resuelve `adb` en este orden: `EVR_ADB_PATH` →
`bin/platform-tools/adb[.exe]` → `$ANDROID_HOME/platform-tools` → `PATH`.
Después reintenta `adb connect` contra `EVR_DEFAULT_SERIAL` (por defecto
`127.0.0.1:4444`, el puerto que `launch-vm` reenvía al 5555 del guest) cada
5 segundos, así que la consola engancha la VM sola en cuanto Android arranca.
Sin dispositivo, la API sigue en pie y responde `online: false` en vez de caerse.

Funciona igual con un **AVD de Android Studio** (`EVR_DEFAULT_SERIAL=emulator-5554`)
o con un **teléfono por USB**.

## Uso: TikTok y "formateo" del emulador

**1) Instalar Android (BlissOS 13/14) una sola vez** en la imagen base:

```powershell
.\scripts\launch-vm.ps1 -Install -Iso .\images\bliss.iso -DiskSizeGB 32
# en GRUB: "Install Bliss-OS to harddisk" -> disco virtio -> instala GApps si el build lo ofrece
```

```bash
./scripts/launch-vm.sh --install --iso images/bliss.iso --disk-size 32
```

**2) Arrancar la VM** (crea el overlay de escritura la primera vez):

```powershell
.\scripts\launch-vm.ps1                 # Windows
./scripts/launch-vm.sh                  # Linux/macOS
```

**3) Instalar TikTok** (elige un camino):

```powershell
# A) desde Google Play (recomendado; requiere GApps en la imagen)
.\scripts\install-app.ps1 -App tiktok -PlayStore
./scripts/install-app.sh --app tiktok --play

# B) sideload de un APK que tú proporciones
.\scripts\install-app.ps1 -Apk .\downloads\tiktok.apk -App tiktok -Launch
./scripts/install-app.sh --apk downloads/tiktok.apk --launch
```

> **TikTok Pro** = cuenta Business/Pro *dentro* de la app (Perfil › Ajustes ›
> Gestionar cuenta › Cambiar a cuenta Business), no un paquete aparte.

**4) "Formatear" el emulador** (volver a estado limpio). Cierra QEMU primero:

```powershell
.\scripts\vm-format.ps1 -Force          # Windows
./scripts/vm-format.sh -Force           # Linux/macOS
```

El patrón **base inmutable + overlay** hace que "formatear" sea recrear
`images/data.qcow2` desde `images/base.qcow2` en segundos. Si dejas TikTok+GApps
instalados en la *base*, cada formateo devuelve un Android limpio pero ya listo.
También hay `-Snapshot <nombre>` (revertir a snapshot) y `-Fresh` (disco vacío).

## Consola web "Elisandro"

Con el middleware corriendo, abre **http://127.0.0.1:5555**:

- **Pantalla en vivo** — el servidor empuja los fotogramas por WebSocket
  (`/ws/video`), sin sondeo HTTP. **Clic = toque**, **arrastrar = deslizar**,
  **rueda = scroll**, y el **teclado físico** escribe en el guest cuando la
  pantalla tiene el foco. Botones ◁ atrás, ○ home, ▢ recientes, ⏻ power, ↵ enter.
  fps ajustable en caliente (2–15).
- **Agent Switcher** — elige el perfil de dispositivo (Pixel 7/8 Pro, Galaxy S23,
  Xiaomi 13) → "Aplicar" reescribe `build.prop` y reinicia. La VM se presenta
  como ese modelo (privacidad: no expone tu PC). Editable en
  `config/device-profiles.json`.
- **Apps** — lanzar TikTok, abrir cualquier paquete, instalar APK, buscar en Play Store.
- **VM** — formatear (overlay/fresh) y estado.

Si el WebSocket de vídeo no está disponible, la consola cae sola a sondeo HTTP de
`/api/screen`, así que sigue funcionando detrás de proxies que no admiten upgrades.

## API del middleware

**REST** (`/api`):

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/health` | estado del servicio y del toolchain (adb, fps, plataforma) |
| GET | `/devices` | dispositivos/VMs conectados |
| POST | `/connect` · `/disconnect` | conectar/desconectar por TCP/IP |
| POST | `/shell` | comando shell en el guest |
| POST | `/input/{tap,swipe,text,key}` | inyección de entrada |
| POST | `/apps/{install,uninstall,launch,play}` | gestión y lanzamiento de apps |
| GET | `/apps/installed?app=` · `/apps/shortcuts` | consulta de paquetes y atajos |
| GET | `/screen` · `/screen/size` | captura PNG y resolución del guest |
| GET | `/vm/status` | estado del emulador + props |
| POST | `/vm/reset` | formatear (`overlay` \| `snapshot` \| `fresh`) |
| GET | `/vm/profiles` · POST `/vm/profile` | agent switcher |

Ejemplos:

```bash
curl http://127.0.0.1:5555/api/health
curl -X POST http://127.0.0.1:5555/api/apps/launch \
     -H "Content-Type: application/json" -d '{"app":"tiktok"}'
curl -X POST http://127.0.0.1:5555/api/vm/reset \
     -H "Content-Type: application/json" -d '{"mode":"overlay"}'
```

**WebSocket de control** (`/ws`): mensajes JSON `tap`, `swipe`, `text`, `key`,
`shell`, `launch`, `status`, `devices`, `ping`. Si incluyes un campo `id`, la
respuesta lo devuelve para correlacionar. El servidor emite eventos `device`
(add/remove/change).

**WebSocket de vídeo** (`/ws/video?serial=…`): el servidor manda un `stream`
inicial (serial, fps, formato), un `size` con la resolución y a partir de ahí
**fotogramas binarios** cuando la pantalla cambia. Control desde el cliente:
`{"type":"fps","value":8}`, `{"type":"pause"}`, `{"type":"resume"}`.

Detalles del canal:

- Un único bucle de captura por serial, compartido entre todas las consolas abiertas.
- Los fotogramas idénticos no se reenvían: con la pantalla quieta el tráfico es ~0.
- Con la red congestionada se descartan fotogramas en vez de acumular retraso.
- El bucle se autorregula: nunca hay dos capturas en vuelo a la vez.

## Configuración

Todo se ajusta por `middleware/.env` (ver `.env.example`): `EVR_PORT`, `EVR_HOST`,
`EVR_ADB_PATH`, `EVR_DEFAULT_SERIAL`, `EVR_AUTOCONNECT_MS`, `EVR_STREAM_FPS`,
`EVR_LOG_LEVEL`.

## Pruebas

```bash
cd middleware && npm test
```

46 pruebas con el runner de Node (sin dependencias de test). Cubren el parseo de
`adb devices`, el entrecomillado de la entrada de texto, la validación de
keycodes y paquetes, el catálogo de perfiles, el motor de streaming (fotogramas
repetidos, cambios de resolución, caída y recuperación del guest, conteo de
suscriptores), toda la API REST y los dos canales WebSocket. Se ejecutan contra
un `adb` simulado (`test-helpers/fake-adb.js`), así que no hacen falta ni Android
ni QEMU.

## Estructura

```
EVR-Emulator/
├── elisandro-setup.ps1          # preflight + bootstrap (Windows)
├── scripts/
│   ├── quickstart.ps1|.sh       # de cero a Android en un comando
│   ├── fetch-binaries.ps1|.sh   # descarga ADB (platform-tools) y scrcpy
│   ├── launch-vm.ps1|.sh        # arranca/instala la VM en QEMU
│   ├── vm-format.ps1|.sh        # "formatea" el emulador
│   └── install-app.ps1|.sh      # instala/lanza apps (TikTok)
├── bin/                         # binarios portables (adb, scrcpy)
├── images/                      # imágenes Android (base.qcow2 + data.qcow2)
├── middleware/                  # servidor Node.js
│   ├── server.js
│   ├── src/{config,logger,adb-service,vm-service,routes}.js
│   ├── src/{ws-bridge,video-bridge,screen-stream,ws-upgrade}.js
│   ├── scripts/doctor.js        # diagnóstico del entorno
│   ├── test/                    # suite de pruebas
│   └── test-helpers/            # adb simulado y generador de PNG
├── frontend/                    # consola web (index.html, app.js, styles.css)
└── config/device-profiles.json  # "agent switcher": perfiles de dispositivo
```

## Roadmap

- **Fase 1** — preflight, middleware base, binarios. ✔
- **Fase 2** — imagen Android: base+overlay, formateo, perfiles de dispositivo
  en `build.prop`, integración de GApps, aceleración gráfica. ✔
- **Fase 3** — streaming: canal `/ws/video` con empuje de fotogramas, fps
  adaptativo y descarte por congestión. ✔ · *pendiente:* pipeline H265 con
  scrcpy y decodificación por WebCodecs para vídeo fluido a 30–60 fps.
- **Fase 4** — consola completa: clic/arrastre/rueda/teclado, agent switcher,
  apps y formateo. ✔ · *pendiente:* audio y portapapeles compartido.

### Alcance / nota de ingeniería

Este proyecto cubre virtualización, QA de apps propias, automatización ADB,
streaming y perfiles de dispositivo para **certificación legítima de Play/GApps**.
No incluye técnicas para evadir los controles de integridad/antifraude de
aplicaciones bancarias (bypass de Play Integrity/SafetyNet ni hooks de
`open()`/`stat()` con ese fin). Para QA de apps que exigen dispositivo
certificado, usa dispositivos reales o farms (p. ej. Firebase Test Lab) y las
herramientas oficiales de prueba de Play Integrity.

Si el Play Store aparece "sin certificar", registra el Android ID en
https://google.com/android/uncertified — es el método **oficial** de Google para
ROMs personalizadas, no un bypass de integridad.
