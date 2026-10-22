import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_check import check_source
from mcl_program_gen import generate_programs


def test_generated_programs_are_valid_unique_and_reproducible():
    progs = generate_programs(15, seed=3)
    assert len(progs) == 15
    assert len(set(progs)) == 15
    assert all(check_source(p).ok for p in progs)
    assert progs == generate_programs(15, seed=3)       # same seed, same output


def test_generated_programs_use_a_mix_of_constructs():
    text = "\n".join(generate_programs(30, seed=5))
    for needle in ["if (", "while (", "print(", "bool ", "int ", "&&", "||", "<="]:
        assert needle in text, needle
