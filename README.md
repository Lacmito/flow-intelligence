# FLOW Intelligence - Cost Dashboard

Scanner automático de servicios/suscripciones + dashboard interactivo con feedback.

## Uso rápido

```bash
# Iniciar el dashboard (escanea + abre en http://localhost:4200)
python3 server.py

# Escanear + abrir dashboard
python3 server.py --scan

# Puerto custom
python3 server.py --port 8080

# Solo escanear (sin server)
python3 scan.py
python3 scan.py --open
python3 scan.py --diff
```

## Dashboard interactivo

El dashboard en `http://localhost:4200` permite:

- **Editar costos reales**: Click en la columna "Costo real/mes" para ingresar el costo mensual de cada servicio
- **Cambiar estado**: Click en la columna "Estado" para marcar como Activo, Revisando, Pausado o Cancelado
- **Agregar feedback**: Click en "+ Agregar feedback" para agregar notas personales
- **Re-escanear**: Botón para ejecutar el scanner sin salir del dashboard
- **Snapshot mensual**: Guarda el costo total del mes actual para tracking histórico
- **Exportar JSON**: Descarga todo el feedback como archivo JSON

## API endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/feedback` | Obtener feedback guardado |
| POST | `/api/feedback/service` | Actualizar un servicio |
| GET | `/api/history` | Historial de snapshots mensuales |
| POST | `/api/snapshot` | Guardar snapshot del mes |
| GET | `/api/scan` | Re-escanear proyectos |

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `server.py` | Server HTTP + API REST para feedback |
| `scan.py` | Scanner que escanea proyectos y genera HTML |
| `template.html` | Template del dashboard (scan.py inyecta datos) |
| `services_config.json` | Configuración: proyectos, servicios, fantasmas, extras |
| `audit.html` | HTML generado (output del scanner) |
| `feedback.json` | Feedback del usuario (costos reales, estados, notas) |
| `cost_history.json` | Historial de snapshots mensuales |
| `.last_scan.json` | Estado del último scan (para detectar cambios) |

## Agregar un servicio nuevo

Editá `services_config.json`:

- **Servicio con API key:** Agregá la variable a `env_patterns` y el servicio a `services`
- **Cobro fantasma:** Agregá a `ghost_services`
- **Servicio sin API key** (hosting, IDE, etc.): Agregá a `extra_services`

## Agregar un proyecto nuevo

Agregá el proyecto en la sección `projects` de `services_config.json`.

## Cron automático

El scanner se ejecuta diariamente a las 9:00 AM. Para cambiar la frecuencia:

```bash
crontab -e
```
