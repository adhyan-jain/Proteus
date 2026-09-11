"""Unit tests for feature_mapper.py. Stdlib-only (unittest), no ryu/mininet dependency --
runs under either .venv or .venv-ryu:

    .venv-ryu/bin/python -m unittest sdn.topology.test_feature_mapper -v
"""
import unittest

from feature_mapper import (
    KNOWN_UNPOPULATED_COLUMNS,
    POPULATED_COLUMNS,
    map_flow_stat_to_schema,
)


class TestMapFlowStatToSchema(unittest.TestCase):
    def test_basic_tcp_flow(self):
        raw = {
            "duration_sec": 2,
            "duration_nsec": 500_000_000,
            "packet_count": 100,
            "byte_count": 64_000,
            "ip_proto": 6,
            "tcp_dst": 443,
        }
        out = map_flow_stat_to_schema(raw)

        self.assertAlmostEqual(out["flow_duration"], 2.5e6)  # 2.5s -> microseconds
        self.assertEqual(out["protocol"], 6)
        self.assertEqual(out["dst_port"], 443)
        self.assertEqual(out["total_fwd_packet"], 100)
        self.assertEqual(out["total_length_of_fwd_packet"], 64_000)
        self.assertAlmostEqual(out["flow_bytes_per_s"], 64_000 / 2.5)
        self.assertAlmostEqual(out["flow_packets_per_s"], 100 / 2.5)
        self.assertAlmostEqual(out["fwd_packets_per_s"], 100 / 2.5)
        self.assertAlmostEqual(out["average_packet_size"], 640.0)
        self.assertAlmostEqual(out["packet_length_mean"], 640.0)

    def test_udp_flow_uses_udp_dst(self):
        raw = {
            "duration_sec": 1, "duration_nsec": 0,
            "packet_count": 10, "byte_count": 1000,
            "ip_proto": 17, "udp_dst": 53,
        }
        out = map_flow_stat_to_schema(raw)
        self.assertEqual(out["dst_port"], 53)
        self.assertEqual(out["protocol"], 17)

    def test_zero_duration_omits_rate_features_not_divides_by_zero(self):
        raw = {"duration_sec": 0, "duration_nsec": 0, "packet_count": 5, "byte_count": 500,
               "ip_proto": 6, "tcp_dst": 80}
        out = map_flow_stat_to_schema(raw)
        self.assertNotIn("flow_bytes_per_s", out)
        self.assertNotIn("flow_packets_per_s", out)
        self.assertNotIn("fwd_packets_per_s", out)
        # non-rate fields still populated
        self.assertEqual(out["total_fwd_packet"], 5)
        self.assertIn("average_packet_size", out)

    def test_zero_packets_omits_size_features(self):
        raw = {"duration_sec": 1, "duration_nsec": 0, "packet_count": 0, "byte_count": 0,
               "ip_proto": 6}
        out = map_flow_stat_to_schema(raw)
        self.assertNotIn("average_packet_size", out)
        self.assertNotIn("packet_length_mean", out)
        self.assertIsNone(out["dst_port"])

    def test_never_fabricates_unpopulated_columns(self):
        raw = {"duration_sec": 3, "duration_nsec": 0, "packet_count": 7, "byte_count": 700,
               "ip_proto": 6, "tcp_dst": 22}
        out = map_flow_stat_to_schema(raw)
        for col in KNOWN_UNPOPULATED_COLUMNS:
            self.assertNotIn(col, out, f"{col} should never be fabricated by this mapper")

    def test_populated_columns_constant_is_a_superset_of_actual_output_keys(self):
        raw = {"duration_sec": 4, "duration_nsec": 0, "packet_count": 3, "byte_count": 300,
               "ip_proto": 6, "tcp_dst": 8080}
        out = map_flow_stat_to_schema(raw)
        self.assertTrue(set(out.keys()).issubset(set(POPULATED_COLUMNS)))

    def test_missing_optional_fields_default_safely(self):
        out = map_flow_stat_to_schema({})
        self.assertEqual(out["total_fwd_packet"], 0)
        self.assertIsNone(out["protocol"])
        self.assertIsNone(out["dst_port"])


if __name__ == "__main__":
    unittest.main()
