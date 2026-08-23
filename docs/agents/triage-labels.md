# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Estado actual en el repo (comprobado 2026-08-22)

`wontfix` **ya existe**: es una de las etiquetas por defecto de GitHub (`#ffffff`).
`triage` debe aplicar esa, no crear una duplicada.

Las otras cuatro no existen todavia. Para crearlas la primera vez:

```bash
gh label create needs-triage    --description "Falta evaluar"                        --color d4c5f9
gh label create needs-info      --description "Esperando informacion de quien reporta" --color fbca04
gh label create ready-for-agent --description "Especificado, listo para un agente"   --color 0e8a16
gh label create ready-for-human --description "Requiere implementacion humana"       --color 1d76db
```

Nadie las ha creado desde aqui a proposito: el remote apunta a
`camiloAndres11/Plumb`, un repo publico de otra cuenta, y crear etiquetas ahi es
un cambio visible para todo el equipo. Corre los comandos cuando lo decidan.

Ojo tambien: el repo es **publico**. Todo issue que estas skills creen es visible
para cualquiera desde el primer segundo. Este proyecto publica indicios sobre
contratacion publica y tiene una regla explicita de vocabulario — "riesgo no es
fraude" — que aplica igual al texto de un issue que al del sitio.
