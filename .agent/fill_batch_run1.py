import json

path = "/home/doblek/open-bfme1/BFME-Translation/.agent/batches/rotwk-run1-2-3bdba0ea0c0f.json"

t = {
"SHC:1": "¡Hola!",
"SHC:2": "Para ganar el mapa tendrás que sobrevivir 23 oleadas OP",
"SHC:HC1": "Has seleccionado el modo Hardcore",
"SHC:HC2": "Necesitarás algo de dinero extra",
"SHC:3": "Me aseguré de que tengas descanso entre las oleadas",
"SHC:4": "¡Disfruta del mapa!",
"SCRIPT:Rest": "Descanso por:",
"TIOS:1": "¡Sauron te observa! Su invasión ha comenzado. ¡Defiende la Tierra Media!",
"TIOS:2": "¡Nada mal! Pero, ¿qué harás contra este ejército?",
"TIOS:3": "¿Crees que eso ya fue todo? ¡Los trasgos te aplastarán!",
"TIOS:4": "¡Sauron es un necio! ¡Yo mismo conquistaré la Tierra Media!",
"TIOS:5": "Tu descanso termina en:",
"TIOS:6": "¡Este es tu fin! ¡La Tierra Media se hundirá en la oscuridad!",
"TIOS:7": "¡Sauron encontró el anillo! Ahora viene a conquistar la Tierra Media",
"TIOS:8": "Sauron llega en:",
"TIOS:9": "¡Felicidades, lo lograste! Tienes permiso para matar a los Hobbits. ¡Buena suerte!",
"TIOS:10": "Los Hobbits llegan en:",
}

with open(path) as f:
    data = json.load(f)

missing = [e["id"] for e in data["entries"] if e["id"] not in t]
print("MISSING:", missing)
for e in data["entries"]:
    if e["id"] in t:
        e["translation"] = t[e["id"]]
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("filled entries, total translations set")