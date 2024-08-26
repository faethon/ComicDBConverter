import os
from datetime import datetime

# Bestandsnaam van het Python script waarin je de versie wilt updaten
filename = 'ComicDBConverter.py'

# Genereer de versie string op basis van de huidige datum en tijd
version = datetime.now().strftime("%Y.%m.%d.%H%M")

# Lees het bestand in en controleer of de versie al bestaat
with open(filename, 'r') as file:
    lines = file.readlines()

version_updated = False

# Open het bestand in schrijfmodus en werk de versie bij of voeg toe
with open(filename, 'w') as file:
    for line in lines:
        if line.startswith('BUILD_DATUM ='):
            file.write(f'BUILD_DATUM = "{version}"\n')
            version_updated = True
        else:
            file.write(line)

    if not version_updated:
        # Als de versie niet bestond, voeg deze dan toe aan het einde van het bestand
        file.write(f'BUILD_DATUM = "{version}"\n')

print(f'Builddate updated to: {version}')
