# BFME-Translation

Proyecto de traducción al español latinoamericano para **Battle for Middle-earth I** (BFME1).

## Descripción

Este repositorio contiene las traducciones de archivos de localización `.str` del juego BFME1, convertidos al formato compatible con el motor SAGE. El archivo de salida compilado es `releases/spanishpatch202.big`.

## Estructura del Proyecto

```
BFME-Translation/
├── catalogs/
│   └── spanish_work.json    # Catálogo principal de traducciones (11,069 entradas)
├── tools/
│   └── localization/
│       ├── validate.py           # Validación estructural del catálogo
│       ├── validate_translation.py # Validación de traducciones
│       ├── build.py              # Compila el catálogo al formato .str
│       └── pack.py               # Empaqueta el .str en .big
├── translations/
│   └── spanish/data/
│       └── lotr.str             # Archivo de salida traducido
├── releases/
│   └── spanishpatch202.big      # Paquete final compilado
├── AGENTS.md                     # Instrucciones para agentes de traducción
└── README.md                     # Este archivo
```

## Cómo Funciona

### Flujo de Trabajo de Traducción

1. **Leer pendientes**: Se lee `catalogs/spanish_work.json` para encontrar entradas con `status: "pending"`.
2. **Traducir**: Se traduce el campo `source` al español latinoamericano en el campo `translation`, se cambia el `status` a `"translated"`, y se registra metadato/historial.
3. **Preservar**: Nunca se modifican IDs, tokens protegidos (`%d`, `%s`), caracteres de control (`\n`) ni tags de engine (`<COL>`).
4. **Validar**: Se ejecutan ambos scripts de validación:
   - `python3 tools/localization/validate.py`
   - `python3 tools/localization/validate_translation.py`
   Si hay errores, se revierte la modificación.
5. **Commit**: Se hace `git add` solo de los archivos modificados y se commit con mensaje convencional (ej: `feat(localization): translate batch 10`).
6. **Sync**: Se sincroniza con el repositorio remoto (`git pull --rebase`, push, pull).

### Flujo de Build (Release)

Cuando se solicita compilar una release:
1. `python3 tools/localization/build.py catalogs/spanish_work.json translations/spanish/data/lotr.str`
2. `python3 tools/localization/pack.py`
3. Verificar que `releases/spanishpatch202.big` se actualice correctamente.

## Progreso Actual

| Métrica            | Valor   |
|--------------------|---------|
| Total de entradas  | 11,069  |
| Traducidas         | 245     |
| Pendientes         | 10,824  |
| **Progreso**       | **2.2%**|

### Historial de Traducciones

| Commit   | Descripción                              |
|----------|------------------------------------------|
| d9282b1  | Fix de 18 entradas no traducidas         |
| 0e21e10  | Lote de 100 entradas traducidas          |
| 9e8433a  | Lote de 10 entradas traducidas           |

## Reglas de Traducción

- **Español latinoamericano**: Usar terminología estándar de LATAM, no España.
- **Preservar formato**: Los wildcards (`%d`, `%s`, `%ls`), saltos de línea (`\n`) y tags de engine (`<COL>`) deben mantenerse intactos.
- **No traducir**: URLs, IDs de entrada, y tokens de formato.
- **Metadatos**: Cada entrada incluye `translation_meta` (origen, modelo, fecha, confianza) y `review` (revisión AI y humana).

## Validación

```bash
python3 tools/localization/validate.py
python3 tools/localization/validate_translation.py
```

Ambos scripts deben retornar `Errors: 0` antes de hacer commit.