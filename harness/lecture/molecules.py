"""Molecules for lectures: a name, formula or SMILES -> a 2-D structure to draw.

RDKit lays the structure out (2-D coordinates, bond orders, Kekulé form). A
name is looked up in a table of common molecules, then on PubChem when online
(cached in .cache/molecules.json). Small molecules show every hydrogen; larger
ones are drawn with implicit hydrogens, as a textbook would.

    python harness/lecture/molecules.py glucose H2O "CC(=O)O"      # resolve and lay out, as JSON
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "molecules.json"

COMMON = {
    "water": "O", "hydrogen": "[H][H]", "oxygen": "O=O", "nitrogen": "N#N", "ozone": "[O-][O+]=O",
    "carbon dioxide": "O=C=O", "carbon monoxide": "[C-]#[O+]", "methane": "C", "ethane": "CC", "propane": "CCC",
    "butane": "CCCC", "ethene": "C=C", "ethylene": "C=C", "ethyne": "C#C", "acetylene": "C#C",
    "methanol": "CO", "ethanol": "CCO", "formaldehyde": "C=O", "acetone": "CC(=O)C", "acetic acid": "CC(=O)O",
    "formic acid": "OC=O", "benzene": "c1ccccc1", "toluene": "Cc1ccccc1", "phenol": "Oc1ccccc1",
    "naphthalene": "c1ccc2ccccc2c1", "ammonia": "N", "hydrogen peroxide": "OO", "hydrochloric acid": "Cl",
    "hydrogen chloride": "Cl", "sulfuric acid": "OS(=O)(=O)O", "sulphuric acid": "OS(=O)(=O)O",
    "nitric acid": "O[N+](=O)[O-]", "carbonic acid": "OC(=O)O", "sodium chloride": "[Na+].[Cl-]",
    "sodium hydroxide": "[Na+].[OH-]", "calcium carbonate": "[Ca+2].[O-]C([O-])=O",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", "fructose": "OC[C@@H]1O[C@](O)(CO)[C@@H](O)[C@@H]1O",
    "sucrose": "OC[C@H]1O[C@@](CO)(O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)[C@@H](O)[C@@H]1O",
    "urea": "NC(N)=O", "glycine": "NCC(=O)O", "alanine": "C[C@H](N)C(=O)O", "adenine": "Nc1ncnc2[nH]cnc12",
    "thymine": "Cc1c[nH]c(=O)[nH]c1=O", "guanine": "Nc1nc2[nH]cnc2c(=O)[nH]1", "cytosine": "Nc1cc[nH]c(=O)n1",
    "uracil": "O=c1cc[nH]c(=O)[nH]1", "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O", "paracetamol": "CC(=O)Nc1ccc(O)cc1", "ibuprofen": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
    "cholesterol": "CC(C)CCC[C@@H](C)[C@H]1CC[C@H]2[C@@H]3CC=C4C[C@@H](O)CC[C@]4(C)[C@H]3CC[C@]12C",
    "lactic acid": "CC(O)C(=O)O", "citric acid": "OC(=O)CC(O)(C(=O)O)CC(=O)O", "ethyl acetate": "CCOC(C)=O",
    "chloroform": "ClC(Cl)Cl", "sodium bicarbonate": "[Na+].OC([O-])=O", "silicon dioxide": "O=[Si]=O",
    "nitrous oxide": "[N-]=[N+]=O", "nitrogen dioxide": "O=[N]=O", "sulfur dioxide": "O=S=O",
    "hydrogen sulfide": "S", "propene": "CC=C", "cyclohexane": "C1CCCCC1", "vitamin c": "OC[C@H](O)[C@H]1OC(=O)C(O)=C1O",
    "ascorbic acid": "OC[C@H](O)[C@H]1OC(=O)C(O)=C1O", "nicotine": "CN1CCC[C@H]1c1cccnc1",
    "dopamine": "NCCc1ccc(O)c(O)c1", "serotonin": "NCCc1c[nH]c2ccc(O)cc12", "adrenaline": "CNC[C@H](O)c1ccc(O)c(O)c1",
}
FORMULAS = {
    "h2o": "water", "h2": "hydrogen", "o2": "oxygen", "n2": "nitrogen", "o3": "ozone", "co2": "carbon dioxide",
    "co": "carbon monoxide", "ch4": "methane", "c2h6": "ethane", "c3h8": "propane", "c2h4": "ethene",
    "c2h2": "ethyne", "ch3oh": "methanol", "c2h5oh": "ethanol", "nh3": "ammonia", "h2o2": "hydrogen peroxide",
    "hcl": "hydrochloric acid", "h2so4": "sulfuric acid", "hno3": "nitric acid", "h2co3": "carbonic acid",
    "nacl": "sodium chloride", "naoh": "sodium hydroxide", "caco3": "calcium carbonate", "c6h12o6": "glucose",
    "c6h6": "benzene", "so2": "sulfur dioxide", "no2": "nitrogen dioxide", "h2s": "hydrogen sulfide",
    "sio2": "silicon dioxide", "n2o": "nitrous oxide", "nahco3": "sodium bicarbonate", "c12h22o11": "sucrose",
}
SMILES_LIKE = re.compile(r"^[A-Za-z0-9@+\-\[\]\(\)=#$/\\%.:*]+$")


def _chem():
    from rdkit import Chem  # noqa: F401 -- an ImportError here is the caller's answer

    return Chem


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower().replace("₂", "2").replace("₃", "3").replace("₄", "4")
                  .replace("₆", "6").replace("₁", "1"))


def _pubchem(name: str) -> str | None:
    if os.environ.get("PANIM_MOLECULES_ONLINE", "1") == "0":
        return None
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if name in cache:
        return cache[name]
    url = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
           f"{urllib.parse.quote(name)}/property/IsomericSMILES,CanonicalSMILES/JSON")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pocketanim-lecture/0.4"})
        with urllib.request.urlopen(request, timeout=10) as response:
            props = json.loads(response.read())["PropertyTable"]["Properties"][0]
        smiles = props.get("IsomericSMILES") or props.get("CanonicalSMILES") or props.get("SMILES")
    except Exception:  # noqa: BLE001 -- offline or unknown: not cached, tried again next time
        return None
    cache[name] = smiles
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return smiles


@lru_cache(None)
def resolve(text: str) -> str | None:
    """SMILES for a name ("glucose"), a formula ("H2O", "C6H12O6") or a SMILES string; None if unknown."""
    Chem = _chem()
    key = _key(text)
    name = FORMULAS.get(key.replace(" ", ""), key)
    if name in COMMON:
        return COMMON[name]
    raw = str(text).strip()
    if SMILES_LIKE.match(raw) and not raw.isalpha() or raw in ("C", "N", "O", "S"):
        if Chem.MolFromSmiles(raw) is not None:
            return raw
    return _pubchem(name)


def find_in_text(text: str) -> list[str]:
    """The molecules a sentence names, in order: what an offline lecture draws."""
    low = " " + _key(text) + " "
    found = []
    for name in sorted(COMMON, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low) and name not in found:
            if not any(name in f for f in found):
                found.append(name)
    for formula, name in FORMULAS.items():
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(formula) + r"(?![a-z0-9])", _key(text).replace(" ", " ")):
            if name not in found and len(formula) > 2:
                found.append(name)
    return found


CPK = {"H": "#F2F2F2", "C": "#404040", "N": "#3050F8", "O": "#FF0D0D", "F": "#90E050", "Cl": "#1FF01F",
       "Br": "#A62929", "I": "#940094", "S": "#FFFF30", "P": "#FF8000", "Na": "#AB5CF2", "K": "#8F40D4",
       "Ca": "#3DFF00", "Mg": "#8AFF00", "Fe": "#E06633", "Si": "#F0C8A0"}


def layout(smiles: str, hydrogens: str = "auto") -> dict:
    """{atoms: [{symbol, x, y, charge, colour}], bonds: [{a, b, order}]}, centred, bond length 1."""
    Chem = _chem()
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"not a molecule: {smiles!r}")
    heavy = mol.GetNumHeavyAtoms()
    if hydrogens == "all" or (hydrogens == "auto" and heavy <= 8):
        mol = Chem.AddHs(mol)
    Chem.Kekulize(mol, clearAromaticFlags=True)
    AllChem.Compute2DCoords(mol)
    conf = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        atoms.append({"symbol": atom.GetSymbol(), "x": pos.x, "y": pos.y, "charge": atom.GetFormalCharge(),
                      "colour": CPK.get(atom.GetSymbol(), "#FF1493")})
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx(), "order": int(b.GetBondTypeAsDouble())}
             for b in mol.GetBonds()]
    if atoms:
        cx = (min(a["x"] for a in atoms) + max(a["x"] for a in atoms)) / 2
        cy = (min(a["y"] for a in atoms) + max(a["y"] for a in atoms)) / 2
        for a in atoms:
            a["x"] -= cx
            a["y"] -= cy
    return {"atoms": atoms, "bonds": bonds, "heavy": heavy, "smiles": smiles}


def formula(smiles: str) -> str:
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    Chem = _chem()
    text = CalcMolFormula(Chem.MolFromSmiles(smiles))
    return text.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))


if __name__ == "__main__":
    out = {}
    for q in sys.argv[1:]:
        smiles = resolve(q)
        out[q] = {"smiles": smiles, "formula": formula(smiles) if smiles else None,
                  "atoms": len(layout(smiles)["atoms"]) if smiles else 0}
    print(json.dumps(out, indent=1, ensure_ascii=False))
