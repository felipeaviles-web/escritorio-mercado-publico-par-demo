import unittest

from demo_par import matching


class TitleFiltersTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"Nombre": "Cambio cilindro desplazamiento Motoniveladora"},
            {"Nombre": "Mejoramiento de Plazas"},
            {"Nombre": "Reposición de luminarias en Plaza del Río"},
            {"Nombre": "Pavimentación de acceso"},
            {"Nombre": "Mejoramiento espacio público Río Rahue"},
        ]

    def test_inclusion_matches_word_prefixes_without_internal_substrings(self):
        criteria = {"incluir": "PLÁZA, paviment, espacio publico", "excluir": "", "hasta": ""}
        self.assertEqual(self.rows[1:], matching(self.rows, criteria))

    def test_exclusion_uses_the_same_boundary(self):
        criteria = {"incluir": "", "excluir": "plaza", "hasta": ""}
        self.assertEqual([self.rows[0], *self.rows[3:]], matching(self.rows, criteria))
