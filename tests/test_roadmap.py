from rkiskaupas_datathon import RoadMap


class TestRoadMap:
    @classmethod
    def setup_class(cls):
        cls.HM = RoadMap.load('tests/HM.json')

    def test_load(self):
        assert len(self.HM.nodes()) == 200
