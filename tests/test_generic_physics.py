import json

import pytest

from backend.engineer_plus.generic_physics import apply_explicit_physics


def _mesh(path):
    path.write_text(
        "\n".join(
            [
                "*NODE",
                "1, 0, 0, 0",
                "2, 1, 0, 0",
                "3, 0, 0, 1",
                "4, 1, 0, 1",
                "*NSET, NSET=BASE",
                "1, 2",
                "*NSET, NSET=TOP",
                "3, 4",
                "*ELEMENT, TYPE=C3D4",
                "1, 1, 2, 3, 4",
            ]
        ),
        encoding="utf-8",
    )


def test_explicit_nodes_and_load_vector_are_preserved(tmp_path):
    source = tmp_path / "mesh.inp"
    output = tmp_path / "physical.inp"
    _mesh(source)

    evidence = apply_explicit_physics(
        source,
        output,
        {
            "youngs_modulus_pa": 2.1e11,
            "poissons_ratio": 0.3,
            "support_nodes": [1, 2],
            "load_nodes": [3, 4],
            "support_dofs": [1, 2],
            "load_vector_n": [100.0, 0.0, -300.0],
        },
    )

    text = output.read_text(encoding="utf-8")
    assert evidence["selection_mode"] == "explicit_nodes"
    assert evidence["per_node_load_vector_n"] == [50.0, 0.0, -150.0]
    assert "AI_PLUS_SUPPORT, 1, 1" in text
    assert "AI_PLUS_SUPPORT, 2, 2" in text
    assert "AI_PLUS_LOAD, 1, 50.0" in text
    assert "AI_PLUS_LOAD, 3, -150.0" in text
    sidecar = json.loads((tmp_path / "physical.inp.physics.json").read_text(encoding="utf-8"))
    assert sidecar["selection_mode"] == "explicit_nodes"


def test_named_sets_are_used_before_extrema_fallback(tmp_path):
    source = tmp_path / "mesh.inp"
    output = tmp_path / "physical.inp"
    _mesh(source)
    evidence = apply_explicit_physics(
        source,
        output,
        {
            "youngs_modulus_pa": 2.1e11,
            "poissons_ratio": 0.3,
            "load_n": 100.0,
            "support_set": "BASE",
            "load_set": "TOP",
        },
    )
    assert evidence["support_nodes"] == [1, 2]
    assert evidence["load_nodes"] == [3, 4]
    assert evidence["selection_mode"] == "named_sets"


def test_invalid_explicit_node_is_rejected(tmp_path):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    with pytest.raises(ValueError, match="absent from mesh"):
        apply_explicit_physics(
            source,
            tmp_path / "physical.inp",
            {
                "youngs_modulus_pa": 2.1e11,
                "poissons_ratio": 0.3,
                "load_vector_n": [0.0, 0.0, 1.0],
                "support_nodes": [999],
                "load_nodes": [3, 4],
            },
        )


def test_generated_alias_sets_preserve_load_distribution(tmp_path):
    source = tmp_path / "mesh.inp"
    source.write_text(
        "*NODE\n1,0,0,0\n2,0,0,1\n** internal mesh comment\n"
        "3,1,0,0\n4,1,0,1\n5,0,1,0\n6,0,1,1\n"
        "*NSET,NSET=BASE,GENERATE\n1,5,2\n"
        "*NSET,NSET=TOP,GENERATE\n2,6,2\n"
        "*NSET,NSET=SUPPORT\nBASE\n*NSET,NSET=LOAD\nTOP\n"
        "*ELEMENT,TYPE=C3D4\n1,1,3,5,2\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    evidence = apply_explicit_physics(source, tmp_path / "physical.inp", {
        "youngs_modulus_pa": 2.1e11, "poissons_ratio": 0.3,
        "support_set": "SUPPORT", "load_set": "LOAD",
        "load_vector_n": [300.0, 0.0, -600.0],
    })
    assert evidence["support_nodes"] == [1, 3, 5]
    assert evidence["load_nodes"] == [2, 4, 6]
    assert evidence["per_node_load_vector_n"] == [100.0, 0.0, -200.0]
    assert source.read_bytes() == before


def test_node_block_sets_and_forward_alias(tmp_path):
    from backend.engineer_plus.generic_physics import _node_sets
    source = tmp_path / "mesh.inp"
    source.write_text(
        "*NSET,NSET=ALIAS\nTOP\n*NODE,NSET=BASE\n1,0,0,0\n2,1,0,0\n"
        "*NODE,NSET=TOP\n3,0,0,1\n4,1,0,1\n*NODE FILE\nU\n",
        encoding="utf-8",
    )
    assert _node_sets(source) == {"TOP": [3, 4], "ALIAS": [3, 4], "BASE": [1, 2]}


@pytest.mark.parametrize("cards,reason", [
    ("*NSET,NSET=A\nB\n*NSET,NSET=B\nA", "cyclic"),
    ("*NSET,NSET=A\nMISSING", "unknown node set"),
    ("*NSET,NSET=A,GENERATE\n1,4,0", "invalid NSET"),
    ("*NSET,NSET=A,GENERATE\n1,4,2", "invalid NSET"),
    ("*NSET,NSET=A,GENERATE\n1,1000000000,1", "exceeds mesh"),
])
def test_invalid_node_sets_do_not_write_physical_deck(tmp_path, cards, reason):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    source.write_text(source.read_text() + "\n" + cards, encoding="utf-8")
    out = tmp_path / "physical.inp"
    with pytest.raises(ValueError, match=reason):
        apply_explicit_physics(source, out, {
            "youngs_modulus_pa": 2.1e11, "poissons_ratio": 0.3, "load_n": 100.0,
            "support_nodes": [1, 2], "load_nodes": [3, 4],
        })
    assert not out.exists()


@pytest.mark.parametrize("unit,expected", [("m", 2.1e11), ("mm", 210000.0)])
def test_solid_material_assignment_and_units(tmp_path, unit, expected):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    before = source.read_bytes()
    out = tmp_path / "physical.inp"
    evidence = apply_explicit_physics(source, out, {
        "youngs_modulus_pa": 2.1e11, "poissons_ratio": 0.3,
        "mesh_length_unit": unit, "load_n": 100.0,
    })
    assert "*SOLID SECTION, ELSET=AI_PLUS_SOLIDS, MATERIAL=AI_PLUS_MATERIAL" in out.read_text()
    assert evidence["material_assignment"]["element_count"] == 1
    assert evidence["material_assignment"]["youngs_modulus_deck"] == expected
    assert source.read_bytes() == before


@pytest.mark.parametrize("youngs,poisson", [(0, 0.3), (-1, 0.3), (float('nan'), 0.3), (210e9, 0.5)])
def test_invalid_material_is_rejected_before_writing(tmp_path, youngs, poisson):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    out = tmp_path / "physical.inp"
    with pytest.raises(ValueError):
        apply_explicit_physics(source, out, {
            "youngs_modulus_pa": youngs, "poissons_ratio": poisson, "load_n": 100,
        })
    assert not out.exists()


def test_existing_material_section_is_not_silently_reassigned(tmp_path):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    source.write_text(source.read_text() + "\n*SOLID SECTION,ELSET=ORIGINAL,MATERIAL=ALLOY\n")
    out = tmp_path / "physical.inp"
    with pytest.raises(ValueError, match="mesh-only"):
        apply_explicit_physics(source, out, {
            "youngs_modulus_pa": 210e9, "poissons_ratio": 0.3, "load_n": 100,
        })
    assert not out.exists()


def test_quadratic_solid_connectivity_continuation():
    from backend.engineer_plus.generic_physics import _solid_element_ids
    text = "*ELEMENT,TYPE=C3D20\n81,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,\n16,17,18,19,20\n"
    assert _solid_element_ids(text, set(range(1, 21))) == [81]


@pytest.mark.parametrize("deck", [
    "*ELEMENT,TYPE=C3D4\n1,1,2,3,999\n",
    "*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n1,1,2,3,4\n",
    "*ELEMENT,TYPE=C3D4\n1,1,2,3,\n*ELSET,ELSET=X\n1\n",
    "*ELEMENT,TYPE=S4\n1,1,2,3,4\n",
])
def test_invalid_or_non_solid_connectivity_rejected(deck):
    from backend.engineer_plus.generic_physics import _solid_element_ids
    with pytest.raises(ValueError):
        _solid_element_ids(deck, {1, 2, 3, 4})


@pytest.mark.parametrize("nodes", [[1.9], [float('inf')], []])
def test_invalid_explicit_support_is_never_coerced_or_replaced(tmp_path, nodes):
    source = tmp_path / "mesh.inp"
    _mesh(source)
    out = tmp_path / "physical.inp"
    with pytest.raises(ValueError):
        apply_explicit_physics(source, out, {
            "youngs_modulus_pa": 2.1e11, "poissons_ratio": 0.3, "load_n": 100.0,
            "support_nodes": nodes,
        })
    assert not out.exists()
