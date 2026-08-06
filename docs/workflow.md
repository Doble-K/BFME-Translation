# Flujo interno de localizacion

Este documento define que herramientas deben usarse en cada etapa. No es
necesario ejecutar todos los scripts en cada lote: cada herramienta tiene un
momento y una responsabilidad concretos.

## Principios

- El catalogo JSON de trabajo es la fuente editable de verdad.
- Los agentes nunca deben abrir un catalogo completo en su contexto.
- Python puede procesar el catalogo localmente; esto no consume contexto de la
  LLM.
- Los agentes trabajan con lotes de 20 entradas por defecto y 100 como maximo.
- Los archivos `.str` y `.big` generados son artefactos, no fuentes editables.
- No se debe ignorar ningun error de validacion.

## 1. Preparar una fuente nueva

Para ROTWK 2.02, la fuente actual es
`sources/englishpatch202_v9.7.7.big`.

Verificar el contenido del paquete:

```bash
tools/big4f/bin/linux/big4f l sources/englishpatch202_v9.7.7.big
```

Debe contener `data/lotr.str`. Extraerlo y convertirlo a JSON:

```bash
tools/big4f/bin/linux/big4f x \
  sources/englishpatch202_v9.7.7.big \
  /tmp/rotwk-source

python3 tools/localization/extract.py \
  /tmp/rotwk-source/data/lotr.str \
  catalogs/english_9770.json
```

Crear el catalogo de trabajo con Gandalf y preservar las entradas del sistema:

```bash
python3 gandalf.py \
  catalogs/english_9770.json \
  catalogs/spanish_9770_work.json

python3 tools/localization/preprocess.py \
  --project config/project.json \
  --write
```

Herramientas obligatorias en esta etapa:

- `big4f l`: verifica que el paquete contenga el `.str` esperado.
- `big4f x`: extrae el archivo sin modificar la fuente.
- `extract.py`: convierte el `.str` CP1252 al catalogo fuente JSON.
- `gandalf.py`: inicializa el catalogo de trabajo.
- `preprocess.py`: preserva `LETTER:*`, `NUMBER:*` y `Version:*`.
- `validate.py`: comprueba la estructura.
- `validate_translation.py`: comprueba los tokens protegidos.

## 2. Traducir con OpenCode

La configuracion local de OpenCode define el agente primario `translator` sin
fijar proveedor ni modelo. Hereda el modelo seleccionado por el usuario y
ofrece estos comandos:

```bash
opencode models
opencode -m PROVIDER/MODEL
```

```text
/translate-next main 20
/translate-all main 100
/translate-parallel rotwk-run1 4 100
/translate-parallel-all rotwk-run2 4 25
/translation-status
/build-candidate
```

`/translate-next` procesa un lote. `/translate-all` continua hasta agotar la
cola o encontrar un bloqueo tecnico. `/translate-parallel` ejecuta una sola
ronda de entre 2 y 8 subagentes con reservas separadas.
`/translate-parallel-all` crea contextos nuevos en cada ronda y continua hasta
completar la cola o detectar un bloqueo seguro. `/build-candidate` valida y
empaqueta solo cuando ya no quedan entradas incompletas ni lotes activos. Al
cambiar `opencode.json` o archivos de `.opencode/`, se debe cerrar y volver a
abrir OpenCode.

Para operar varios modelos de forma desatendida, la matriz explicita se define
en `config/opencode_farm.json`. Primero se pueden revisar los comandos sin
iniciar procesos y luego arrancar el supervisor en segundo plano:

```bash
python3 tools/localization/opencode_farm.py start \
  --config config/opencode_farm.json --dry-run
python3 tools/localization/opencode_farm.py start \
  --config config/opencode_farm.json --detach
```

Comprobar el estado, detener la granja o limpiar leases huerfanos de sus
prefixes configurados:

```bash
python3 tools/localization/opencode_farm.py status \
  --config config/opencode_farm.json
python3 tools/localization/opencode_farm.py stop \
  --config config/opencode_farm.json
python3 tools/localization/opencode_farm.py clean \
  --config config/opencode_farm.json
```

Cada coordinador ejecuta una ronda acotada de `/translate-parallel`; el
supervisor crea una sesion nueva para la siguiente ronda. `stop` termina los
procesos antes de liberar leases y `clean` rechaza una granja todavia activa.
La granja usa el agente `translation-coordinator`, que no tiene permiso para
exportar ni aplicar batches. Ademas, `agent_batch.py` acepta solamente los
labels exactos `PREFIX-1` a `PREFIX-WORKERS` dentro de cada proceso supervisado.

Los agentes de traduccion deniegan automaticamente cualquier comando shell que
no pertenezca a la lista fija de herramientas de localizacion. Para leer y
editar batches usan directamente `Read` y `Edit`; no deben solicitar permisos
para `ls`, `python3 -c` ni otros comandos auxiliares.

Exportar un lote pequeno. El modo `incomplete` incluye entradas pendientes y
placeholders exactos registrados por el pipeline:

```bash
python3 tools/localization/agent_batch.py export \
  --project config/project.json \
  --mode incomplete \
  --count 20 \
  --worker worker-1
```

La herramienta imprime `BATCH_FILE` y `RESPONSE_FILE`. OpenCode lee el batch sin
editarlo y completa solamente los valores `translation` de la respuesta. No
debe crear scripts auxiliares ni reconstruir el batch.

Aplicar el lote:

```bash
python3 tools/localization/agent_batch.py apply \
  --project config/project.json \
  --input BATCH_FILE \
  --response RESPONSE_FILE \
  --actor worker-1 \
  --model MODELO_UTILIZADO
```

`agent_batch.py export` reserva las entradas durante seis horas de forma
predeterminada. Distintos workers que compartan el mismo checkout reciben lotes
sin IDs superpuestos. `agent_batch.py apply` valida la reserva, el batch
inmutable y la respuesta completa antes de escribir. Rechaza reservas vencidas,
manifiestos alterados, respuestas truncadas, entradas obsoletas, IDs cambiados,
hashes diferentes, traducciones vacias y tokens protegidos incorrectos. Las
entradas generadas por una LLM quedan con `needs_review`.

Comandos de coordinacion:

```bash
python3 tools/localization/agent_batch.py status \
  --project config/project.json --mode incomplete --json

python3 tools/localization/agent_batch.py renew \
  --project config/project.json --input BATCH_FILE

python3 tools/localization/agent_batch.py release \
  --project config/project.json --input BATCH_FILE

python3 tools/localization/agent_batch.py reset-response \
  --project config/project.json --input BATCH_FILE
```

Para observar el porcentaje, la velocidad y los workers desde otra terminal:

```bash
python3 tools/localization/watch_progress.py \
  --project config/project.json \
  --interval 10
```

El monitor es de solo lectura, se actualiza cada diez segundos de forma
predeterminada y se detiene con `Ctrl+C`. El ritmo usa una ventana movil de cinco
minutos y la estimacion restante solo aparece cuando hubo avance reciente. La
opcion `--rate-window` permite cambiar esa ventana en minutos.

Si el JSON del lote quedo corrupto, se puede liberar sin leerlo usando los
valores mostrados por `status`:

```bash
python3 tools/localization/agent_batch.py release \
  --project config/project.json \
  --batch-id BATCH_ID \
  --worker WORKER_NAME
```

Los leases son locales al checkout. Para agentes en otras maquinas o clones se
necesita una cola compartida externa; no se deben sincronizar archivos de lease
mediante Git.

La correccion manual de Gandalf y `translate.py --edit` puede convivir con una
granja activa. Cada guardado vuelve a cargar el catalogo bajo el mismo lock y
modifica solamente su estado mas reciente. Una entrada reservada por un batch o
modificada desde que se abrio se rechaza sin escribir; se debe actualizar la
vista y volver a intentarlo. Gandalf tambien permite devolver una entrada a la
cola, preservarla de forma explicita o marcar su review como completado.

Despues de cada lote se deben ejecutar ambos validadores:

```bash
python3 tools/localization/validate.py --project config/project.json
python3 tools/localization/validate_translation.py --project config/project.json
```

Ambos deben terminar con cero errores. Las advertencias conocidas por IDs
duplicados no equivalen a errores, pero deben permanecer visibles.

## 3. Normalizar y revisar

Antes de una compilacion final:

```bash
python3 tools/localization/normalize_hotkeys.py \
  --project config/project.json \
  --write

python3 tools/localization/validate.py --project config/project.json
python3 tools/localization/validate_translation.py --project config/project.json
```

Usar `review.py` o el modo de revision manual solamente cuando corresponda
aprobar, rechazar o cerrar una revision. No usar `migrate_catalog.py` sobre un
catalogo nuevo; existe para esquemas antiguos.

## 4. Construir y empaquetar

El build normal es estricto y debe ejecutarse cuando la traduccion requerida
este completa:

```bash
python3 tools/localization/build.py --project config/project.json
python3 tools/localization/pack.py --project config/project.json
```

`pack.py` vuelve a extraer el paquete generado y verifica sus archivos, bytes,
IDs y cantidades. El resultado esperado es `releases/spanishpatch202.big`.

Para una prueba parcial se permite explicitamente el texto fuente como
fallback:

```bash
python3 tools/localization/build.py \
  --project config/project.json \
  --allow-source-fallback

python3 tools/localization/pack.py --project config/project.json
```

Nunca usar `--allow-source-fallback` para una publicacion.

## 5. Herramientas condicionales

- `update.py`: solo cuando cambia el `.str` ingles de referencia.
- `compare.py`: para comparar idiomas o versiones antes de actualizar.
- `normalize_hotkeys.py`: despues de traducir y antes del build final.
- `review.py`: para decisiones explicitas de revision.
- `migrate_catalog.py`: solo para catalogos con un esquema antiguo.
- `ai_translate.py`: proveedor heredado; Gandalf y el flujo activo de OpenCode
  no dependen de Ollama.
- `build.py`: build estricto final o prueba parcial explicita.
- `pack.py`: unicamente despues de generar el `.str`.

## 6. Pruebas de regresion

Despues de cambiar herramientas o el esquema del catalogo:

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas no sustituyen los dos validadores del catalogo ni la prueba manual
dentro del juego.

## 7. Escalamiento de herramientas

Durante una traduccion masiva, el agente puede encontrar limitaciones que
deberian resolverse como herramientas reutilizables. Ejemplos:

- deteccion insuficiente de texto que sigue en ingles;
- un nuevo tipo de token o etiqueta SAGE;
- varios `.str` dentro del mismo mod;
- trabajo manual repetido que pueda automatizarse de forma determinista;
- falta de un informe de estado o de una validacion;
- incompatibilidad reproducible con una nueva version de un mod.

El agente debe detener el lote afectado y proponer una herramienta cuando
continuar implique perder datos, debilitar validaciones o repetir trabajo a
gran escala. La propuesta debe incluir problema reproducible, severidad,
interfaz CLI minima, compatibilidad, pruebas y criterio de finalizacion.

Puede implementar directamente una mejora pequena si es compatible, no migra
ni reescribe traducciones y queda cubierta por pruebas. Debe solicitar
aprobacion antes de:

- cambiar la semantica o el esquema del catalogo;
- ejecutar una migracion masiva;
- eliminar o reemplazar datos existentes;
- cambiar el contenido final del paquete de forma no localizada;
- agregar servicios externos o dependencias nuevas.

Una herramienta urgente no debe incorporarse como logica especifica de un solo
catalogo. Debe aceptar `--project` cuando corresponda y servir para otros juegos
o mods SAGE, incluido un proceso inicial masivo como Age of the Ring.
