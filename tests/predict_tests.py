from datetime import datetime
from dateutil.parser import parse
from dateutil.tz import tzutc
import json
import os
import unittest

from openapscontrib.predict.predict import Schedule
from openapscontrib.predict.predict import calculate_carb_effect
from openapscontrib.predict.predict import calculate_cob
from openapscontrib.predict.predict import calculate_glucose_from_effects
from openapscontrib.predict.predict import calculate_insulin_effect
from openapscontrib.predict.predict import calculate_iob
from openapscontrib.predict.predict import calculate_momentum_effect
from openapscontrib.predict.predict import future_glucose
from openapscontrib.predict.predict import glucose_data_tuple


def get_file_at_path(path):
    return "{}/{}".format(os.path.dirname(os.path.realpath(__file__)), path)


class GlucoseDataTupleTestCase(unittest.TestCase):
    def test_nightscout_naive_entry(self):
        date, glucose = glucose_data_tuple({
            "_id": "5637e1b7313de36876dbdd0a",
            "device": "xDrip-DexbridgeWixel",
            "date": 1446502839045,
            "display_time": "2015-11-02 23:20:39.045 ",
            "glucose": 131,
            "trend_arrow": "Flat",
            "type": "glucose",
            "filtered": 139648,
            "unfiltered": 137792,
            "rssi": 100,
            "noise": 1
        })

        self.assertEqual(datetime(2015, 11, 2, 23, 20, 39, 45000), parse(date))
        self.assertEqual(131, glucose)

    def test_nightscount_aware_entry(self):
        date, glucose = glucose_data_tuple({
            "_id": "562977cc1c1181016e00554c",
            "device": "dexcom",
            "date": 1445558216000,
            "dateString": "2015-07-13T10:00:00+00:00",
            "direction": "Flat",
            "noise": 1,
            "type": "sgv",
            "filtered": 168640,
            "unfiltered": 168032,
            "rssi": 205,
            "glucose": 150
        })

        self.assertEqual(datetime(2015, 07, 13, 10, tzinfo=tzutc()), parse(date))
        self.assertEqual(150, glucose)

    def test_medtronic_entry(self):
        date, glucose = glucose_data_tuple({
            "name": "GlucoseSensorData",
            "date_type": "prevTimestamp",
            "_tell": 9,
            "sgv": 142,
            "date": "2015-07-28T23:01:00",
            "packet_size": 0,
            "op": 71
        })

        self.assertEqual(datetime(2015, 07, 28, 23, 1), parse(date))
        self.assertEqual(142, glucose)

    def test_dexcom_reader_entry(self):
        date, glucose = glucose_data_tuple({
            "trend_arrow": "FLAT",
            "system_time": "2015-11-05T03:50:09",
            "display_time": "2015-11-04T19:51:34",
            "glucose": 143
        })

        self.assertEqual(datetime(2015, 11, 4, 19, 51, 34), parse(date))
        self.assertEqual(143, glucose)


class FutureGlucoseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(get_file_at_path("fixtures/read_carb_ratios.json")) as fp:
            cls.carb_ratios = json.load(fp)

        with open(get_file_at_path("fixtures/read_insulin_sensitivies.json")) as fp:
            cls.insulin_sensitivities = json.load(fp)

    def test_single_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T12:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T12:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictContainsSubset({'date': '2015-07-13T16:10:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(110.0, glucose[-1]['amount'])

    def test_multiple_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T10:00:00",
                "end_at": "2015-07-13T10:00:00",
                "amount": 1.0,
                "unit": "U"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T11:00:00",
                "end_at": "2015-07-13T11:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T10:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T10:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictContainsSubset({'date': '2015-07-13T15:10:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(70.0, glucose[-1]['amount'])

    def test_aware_dates(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T10:00:00+00:00",
                "end_at": "2015-07-13T11:00:00+00:00",
                "amount": 1.0,
                "unit": "U/hour"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T11:00:00+00:00",
                "end_at": "2015-07-13T11:00:00+00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        normalized_glucose = [
            {
                "_id": "562977cc1c1181016e00554c",
                "device": "dexcom",
                "date": 1445558216000,
                "dateString": "2015-07-13T10:00:00+00:00",
                "direction": "Flat",
                "noise": 1,
                "type": "sgv",
                "filtered": 168640,
                "unfiltered": 168032,
                "rssi": 205,
                "glucose": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T10:00:00+00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictContainsSubset({'date': '2015-07-13T15:10:00+00:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(70.0, glucose[-1]['amount'])

    def test_future_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T12:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T11:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T11:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[1])
        self.assertDictContainsSubset({'date': '2015-07-13T16:10:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(110.0, glucose[-1]['amount'])

    def test_square_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T12:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertEqual('2015-07-13T17:10:00', glucose[-1]['date'])
        self.assertAlmostEqual(110.0, glucose[-1]['amount'])

    def test_future_square_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T11:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T11:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[1])
        self.assertDictContainsSubset({'date': '2015-07-13T13:00:00', 'unit': 'mg/dL'}, glucose[13])
        self.assertAlmostEqual(146.87, glucose[13]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T17:10:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(110.0, glucose[-1]['amount'])

    def test_carb_completion_with_ratio_change(self):
        normalized_history = [
            {
                "type": "Meal",
                "start_at": "2015-07-15T14:30:00",
                "end_at": "2015-07-15T14:30:00",
                "amount": 9,
                "unit": "g"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-15T14:30:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictContainsSubset({'date': '2015-07-15T18:40:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(190.0, glucose[-1]['amount'])

    def test_basal_dosing_end(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-17T12:00:00",
                "end_at": "2015-07-17T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-17T12:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule']),
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertDictContainsSubset({'date': '2015-07-17T17:10:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(130, glucose[-1]['amount'], delta=1)

    def test_no_input_history(self):
        normalized_history = []

        normalized_glucose = [
            {
                "date": "2015-07-17T12:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule']),
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertEqual([{'date': '2015-07-17T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}], glucose)

    def test_no_input_glucose(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-17T12:00:00",
                "end_at": "2015-07-17T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        normalized_glucose = [
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule']),
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertListEqual([], glucose)

    def test_single_bolus_with_excercise_marker(self):
        normalized_history = [
            {
                "start_at": "2015-07-13T12:05:00",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-07-13T12:05:00",
                "amount": 1,
                "type": "Exercise",
                "unit": "event"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T12:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-07-13T12:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictContainsSubset({'date': '2015-07-13T16:15:00', 'unit': 'mg/dL'}, glucose[-1])
        self.assertAlmostEqual(110.0, glucose[-1]['amount'])

    def test_fake_unit(self):
        normalized_history = [
            {
                "start_at": "2015-09-07T22:23:08",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-09-07T22:23:08",
                "amount": 1,
                "type": "Exercise",
                "unit": "beer"
            }
        ]

        normalized_glucose = [
            {
                "date": "2015-09-07T23:00:00",
                "sgv": 150
            }
        ]

        glucose = future_glucose(
            normalized_history,
            normalized_glucose,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            Schedule(self.carb_ratios['schedule'])
        )

        self.assertDictEqual({'date': '2015-09-07T23:00:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[0])
        self.assertDictEqual({'date': '2015-09-08T02:35:00', 'amount': 150.0, 'unit': 'mg/dL'}, glucose[-1])


class CalculateCarbEffectTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(get_file_at_path("fixtures/read_insulin_sensitivies.json")) as fp:
            cls.insulin_sensitivities = json.load(fp)

        with open(get_file_at_path("fixtures/read_carb_ratios.json")) as fp:
            cls.carb_ratios = json.load(fp)

    def test_carb_completion_with_ratio_change(self):
        normalized_history = [
            {
                "type": "Meal",
                "start_at": "2015-07-15T14:30:00",
                "end_at": "2015-07-15T14:30:00",
                "amount": 9,
                "unit": "g"
            }
        ]

        effect = calculate_carb_effect(
            normalized_history,
            Schedule(self.carb_ratios['schedule']),
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-15T17:40:00', 'amount': 40.0, 'unit': 'mg/dL'}, effect[-1])

    def test_no_input_history(self):
        normalized_history = []

        effect = calculate_carb_effect(
            normalized_history,
            Schedule(self.carb_ratios['schedule']),
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertListEqual([], effect)

    def test_fake_unit(self):
        normalized_history = [
            {
                "start_at": "2015-09-07T22:23:08",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-09-07T22:23:08",
                "amount": 1,
                "type": "Exercise",
                "unit": "beer"
            }
        ]

        effect = calculate_carb_effect(
            normalized_history,
            Schedule(self.carb_ratios['schedule']),
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-09-07T22:20:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictEqual({'date': '2015-09-08T01:35:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[-1])

    def test_complicated_history(self):
        with open(get_file_at_path("fixtures/carb_effect_from_history_input.json")) as fp:
            normalized_history = json.load(fp)
        with open(get_file_at_path("fixtures/carb_effect_from_history_output.json")) as fp:
            expected_output = json.load(fp)

        effect = calculate_carb_effect(
            normalized_history,
            Schedule(self.carb_ratios['schedule']),
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertListEqual(
            expected_output,
            effect
        )


class CalculateCOBTestCase(unittest.TestCase):
    def test_carb_completion(self):
        normalized_history = [
            {
                "type": "Meal",
                "start_at": "2015-07-15T14:30:00",
                "end_at": "2015-07-15T14:30:00",
                "amount": 9,
                "unit": "g"
            }
        ]

        effect = calculate_cob(
            normalized_history
        )

        self.assertDictEqual({'date': '2015-07-15T17:40:00', 'amount': 0.0, 'unit': 'g'}, effect[-1])

    def test_no_input_history(self):
        normalized_history = []

        effect = calculate_cob(
            normalized_history
        )

        self.assertListEqual([], effect)

    def test_fake_unit(self):
        normalized_history = [
            {
                "start_at": "2015-09-07T22:23:08",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-09-07T22:23:08",
                "amount": 1,
                "type": "Exercise",
                "unit": "beer"
            }
        ]

        effect = calculate_cob(
            normalized_history
        )

        self.assertDictEqual({'date': '2015-09-07T22:20:00', 'amount': 0.0, 'unit': 'g'}, effect[0])
        self.assertDictEqual({'date': '2015-09-08T01:35:00', 'amount': 0.0, 'unit': 'g'}, effect[-1])

    def test_complicated_history(self):
        with open(get_file_at_path("fixtures/carb_effect_from_history_input.json")) as fp:
            normalized_history = json.load(fp)
        with open(get_file_at_path("fixtures/carbs_on_board_output.json")) as fp:
            expected_output = json.load(fp)

        effect = calculate_cob(
            normalized_history
        )

        self.assertListEqual(
            expected_output,
            effect
        )


class CalculateInsulinEffectTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(get_file_at_path("fixtures/read_insulin_sensitivies.json")) as fp:
            cls.insulin_sensitivities = json.load(fp)

    def test_single_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:01:32",
                "end_at": "2015-07-13T12:01:32",
                "amount": 1.5,
                "unit": "U"
            }
        ]

        with open(get_file_at_path('fixtures/effect_from_bolus_output.json')) as fp:
            expected = json.load(fp)

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertListEqual(
            [{'date': x['date'], 'amount': round(x['amount'], 13), 'unit': x['unit']} for x in expected],
            [{'date': x['date'], 'amount': round(x['amount'], 13), 'unit': x['unit']} for x in effect]
        )

    def test_short_temp_basal(self):
        normalized_history = [
            {
                'type': 'TempBasal',
                'start_at': '2015-07-13T12:01:32',
                'end_at': '2015-07-13T12:06:32',
                'amount': 12.0,
                'unit': 'U/hour'
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictEqual({'date': '2015-07-13T16:20:00', 'amount': -40.0, 'unit': 'mg/dL'}, effect[-1])

    def test_datetime_rounding(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:02:37",
                "end_at": "2015-07-13T12:02:37",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-07-13T12:15:00', 'unit': 'mg/dL'}, effect[3])
        self.assertAlmostEqual(-0.12, effect[3]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T16:15:00', 'amount': -40.0, 'unit': 'mg/dL'}, effect[-1])

    def test_datetime_rounding_basal(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T12:02:37",
                "end_at": "2015-07-13T12:07:37",
                "amount": 12.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-07-13T12:15:00', 'unit': 'mg/dL'}, effect[3])
        self.assertAlmostEqual(-0.12, effect[3]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T16:20:00', 'amount': -40.0, 'unit': 'mg/dL'}, effect[-1])

    def test_irregular_basal_duration(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T12:02:37",
                "end_at": "2015-07-13T12:05:16",
                "amount": 22.641509433962263,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-07-13T12:15:00', 'unit': 'mg/dL'}, effect[3])
        self.assertAlmostEqual(-0.12, effect[3]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T16:20:00', 'unit': 'mg/dL'}, effect[-1])
        self.assertAlmostEqual(-40.0, effect[-1]['amount'], delta=0.01)

    def test_multiple_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T10:00:00",
                "end_at": "2015-07-13T10:00:00",
                "amount": 1.0,
                "unit": "U"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T11:00:00",
                "end_at": "2015-07-13T11:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-07-13T10:00:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictEqual({'date': '2015-07-13T15:10:00', 'amount': -80.0, 'unit': 'mg/dL'}, effect[-1])

    def test_square_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        with open(get_file_at_path('fixtures/effect_from_square_bolus_output.json')) as fp:
            expected = json.load(fp)

        self.assertListEqual(expected, effect)

        self.assertDictContainsSubset({'date': '2015-07-13T12:10:00', 'unit': 'mg/dL'}, effect[2])
        self.assertAlmostEqual(-1.06, effect[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T17:10:00', 'amount': -40.0, 'unit': 'mg/dL'}, effect[-1])
        self.assertEqual('2015-07-13T13:50:00', effect[22]['date'])
        self.assertAlmostEqual(-13.37, effect[24]['amount'], delta=0.01)

    def test_two_square_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T07:00:00",
                "end_at": "2015-07-13T08:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictContainsSubset({'date': '2015-07-13T07:10:00', 'unit': 'mg/dL'}, effect[2])
        self.assertAlmostEqual(-1.06, effect[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T17:10:00', 'amount': -80.0, 'unit': 'mg/dL'}, effect[-1])
        self.assertEqual('2015-07-13T08:50:00', effect[22]['date'])
        self.assertAlmostEqual(-13.37, effect[24]['amount'], delta=0.01)

    def test_overlapping_basals(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T08:00:00",
                "end_at": "2015-07-13T09:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            },
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T07:00:00",
                "end_at": "2015-07-13T08:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictContainsSubset({'date': '2015-07-13T07:10:00', 'unit': 'mg/dL'}, effect[2])
        self.assertAlmostEqual(-1.07, effect[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T13:10:00', 'amount': -80.0, 'unit': 'mg/dL'}, effect[-1])
        self.assertEqual('2015-07-13T08:50:00', effect[22]['date'])
        self.assertAlmostEqual(-16.50, effect[24]['amount'], delta=0.01)

    def test_counteracting_basals(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T08:00:00",
                "end_at": "2015-07-13T09:00:00",
                "amount": -1.0,
                "unit": "U/hour"
            },
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T07:00:00",
                "end_at": "2015-07-13T08:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictContainsSubset({'date': '2015-07-13T07:10:00', 'unit': 'mg/dL'}, effect[2])
        self.assertAlmostEqual(-1.06, effect[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T13:10:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[-1])
        self.assertEqual('2015-07-13T08:50:00', effect[22]['date'])
        self.assertAlmostEqual(-10.25, effect[24]['amount'], delta=0.01)

    def test_insulin_effect_with_sensf_change(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-15T14:30:00",
                "end_at": "2015-07-15T14:30:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule([
                {
                    "i": 0,
                    "start": "00:00:00",
                    "sensitivity": 40,
                    "offset": 0,
                    "x": 0
                },
                {
                    "i": 1,
                    "start": "16:00:00",
                    "sensitivity": 10,
                    "offset": 450,
                    "x": 450
                }
            ])
        )

        self.assertDictEqual({'date': '2015-07-15T18:40:00', 'amount': -40.0, 'unit': 'mg/dL'}, effect[-1])

    def test_basal_dosing_end(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-17T12:00:00",
                "end_at": "2015-07-17T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertEqual('2015-07-17T17:10:00', effect[-1]['date'])
        self.assertAlmostEqual(-20.0, effect[-1]['amount'])

    def test_no_input_history(self):
        normalized_history = []

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities']),
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertListEqual([], effect)

    def test_fake_unit(self):
        normalized_history = [
            {
                "start_at": "2015-09-07T22:23:08",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-09-07T22:23:08",
                "amount": 1,
                "type": "Exercise",
                "unit": "beer"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-09-07T22:20:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])
        self.assertDictEqual({'date': '2015-09-08T02:35:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[-1])

    def test_negative_temp_basals(self):
        normalized_history = [
            {
                "amount": -0.8,
                "start_at": "2015-10-15T20:39:52",
                "description": "TempBasal: 0.0U/hour over 20min",
                "type": "TempBasal",
                "unit": "U/hour",
                "end_at": "2015-10-15T20:59:52"
            },
            {
                "amount": -0.75,
                "start_at": "2015-10-15T20:34:34",
                "description": "TempBasal: 0.05U/hour over 5min",
                "type": "TempBasal",
                "unit": "U/hour",
                "end_at": "2015-10-15T20:39:34"
            }
        ]

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertDictEqual({'date': '2015-10-15T20:30:00', 'amount': 0.0, 'unit': 'mg/dL'}, effect[0])

        self.assertDictContainsSubset({'date': '2015-10-15T22:40:00', 'unit': 'mg/dL'}, effect[26])
        self.assertAlmostEqual(5.97, effect[26]['amount'], delta=0.01)

        self.assertEqual('2015-10-16T01:10:00', effect[-1]['date'])
        self.assertAlmostEqual(13.16, effect[-1]['amount'], delta=0.01)

    def test_complicated_history(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        with open(get_file_at_path('fixtures/effect_from_history_output.json')) as fp:
            expected = json.load(fp)

        effect = calculate_insulin_effect(
            normalized_history,
            4,
            Schedule(self.insulin_sensitivities['sensitivities'])
        )

        self.assertListEqual(expected, effect)


class CalculateIOBTestCase(unittest.TestCase):
    def test_single_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T12:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 1.0, 'unit': 'U'}, iob[0])
        self.assertDictContainsSubset({'date': '2015-07-13T12:20:00', 'unit': 'U'}, iob[4])
        self.assertAlmostEqual(0.98, iob[4]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T16:10:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])

    def test_datetime_rounding(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:02:37",
                "end_at": "2015-07-13T12:02:37",
                "amount": 1.5,
                "unit": "U"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4
        )

        with open(get_file_at_path("fixtures/iob_from_bolus_output.json")) as fp:
            expected_output = json.load(fp)

        self.assertListEqual(expected_output, iob)

    def test_multiple_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T10:00:00",
                "end_at": "2015-07-13T10:00:00",
                "amount": 1.0,
                "unit": "U"
            },
            {
                "type": "Bolus",
                "start_at": "2015-07-13T11:00:00",
                "end_at": "2015-07-13T11:00:00",
                "amount": 1.0,
                "unit": "U"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4
        )

        self.assertDictEqual({'date': '2015-07-13T10:00:00', 'amount': 1.0, 'unit': 'U'}, iob[0])
        self.assertDictContainsSubset({'date': '2015-07-13T10:20:00'}, iob[4])
        self.assertAlmostEqual(0.98, iob[4]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T11:00:00'}, iob[12])
        self.assertAlmostEqual(1.85, iob[12]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T12:00:00'}, iob[24])
        self.assertAlmostEqual(1.37, iob[24]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T15:10:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])

    def test_square_bolus(self):
        normalized_history = [
            {
                "type": "Bolus",
                "start_at": "2015-07-13T12:00:00",
                "end_at": "2015-07-13T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4,
            visual_iob_only=False
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'U'}, iob[0])
        self.assertDictContainsSubset({'date': '2015-07-13T12:10:00', 'unit': 'U'}, iob[2])
        self.assertAlmostEqual(0.083, iob[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T17:10:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])
        self.assertEqual('2015-07-13T13:50:00', iob[22]['date'])
        self.assertAlmostEqual(0.67, iob[24]['amount'], delta=0.01)

        iob = calculate_iob(
            normalized_history,
            4,
            visual_iob_only=True
        )

        self.assertDictContainsSubset({'date': '2015-07-13T12:00:00', 'unit': 'U'}, iob[0])
        self.assertAlmostEqual(0.083, iob[0]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T12:10:00', 'unit': 'U'}, iob[2])
        self.assertAlmostEqual(0.25, iob[2]['amount'], delta=0.01)
        self.assertDictEqual({'date': '2015-07-13T17:10:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])
        self.assertEqual('2015-07-13T13:50:00', iob[22]['date'])
        self.assertAlmostEqual(0.67, iob[24]['amount'], delta=0.01)

    def test_irregular_basal_duration(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-13T12:02:37",
                "end_at": "2015-07-13T12:05:16",
                "amount": 22.641509433962263,
                "unit": "U/hour"
            }
        ]

        effect = calculate_iob(
            normalized_history,
            4,
            visual_iob_only=False
        )

        self.assertDictEqual({'date': '2015-07-13T12:00:00', 'amount': 0.0, 'unit': 'U'}, effect[0])
        self.assertDictEqual({'date': '2015-07-13T12:05:00', 'amount': 0.0, 'unit': 'U'}, effect[1])
        self.assertDictEqual({'date': '2015-07-13T12:10:00', 'amount': 0.0, 'unit': 'U'}, effect[2])
        self.assertDictContainsSubset({'date': '2015-07-13T12:15:00', 'unit': 'U'}, effect[3])
        self.assertAlmostEqual(1.00, effect[3]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T14:10:00', 'unit': 'U'}, effect[26])
        self.assertAlmostEqual(0.48, effect[26]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-07-13T16:20:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(0.0, effect[-1]['amount'], delta=0.01)

    def test_carb_completion_with_ratio_change(self):
        normalized_history = [
            {
                "type": "Meal",
                "start_at": "2015-07-15T14:30:00",
                "end_at": "2015-07-15T14:30:00",
                "amount": 9,
                "unit": "g"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4
        )

        self.assertDictEqual({'date': '2015-07-15T14:30:00', 'amount': 0.0, 'unit': 'U'}, iob[0])
        self.assertDictEqual({'date': '2015-07-15T18:40:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])

    def test_basal_dosing_end(self):
        normalized_history = [
            {
                "type": "TempBasal",
                "start_at": "2015-07-17T12:00:00",
                "end_at": "2015-07-17T13:00:00",
                "amount": 1.0,
                "unit": "U/hour"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4,
            basal_dosing_end=datetime(2015, 7, 17, 12, 30),
            visual_iob_only=False
        )

        self.assertDictEqual({'date': '2015-07-17T17:10:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])
        self.assertDictEqual({'date': '2015-07-17T12:00:00', 'amount': 0.0, 'unit': 'U'}, iob[0])
        self.assertDictEqual({'date': '2015-07-17T16:40:00', 'amount': 0.0, 'unit': 'U'}, iob[-7])
        self.assertDictContainsSubset({'date': '2015-07-17T12:40:00', 'unit': 'U'}, iob[8])
        self.assertAlmostEqual(0.48, iob[8]['amount'], delta=0.01)

    def test_no_input_history(self):
        normalized_history = []

        iob = calculate_iob(
            normalized_history,
            4,
            basal_dosing_end=datetime(2015, 7, 17, 12, 30)
        )

        self.assertListEqual([], iob)

    def test_fake_unit(self):
        normalized_history = [
            {
                "start_at": "2015-09-07T22:23:08",
                "description": "JournalEntryExerciseMarker",
                "end_at": "2015-09-07T22:23:08",
                "amount": 1,
                "type": "Exercise",
                "unit": "beer"
            }
        ]

        iob = calculate_iob(
            normalized_history,
            4
        )

        self.assertDictEqual({'date': '2015-09-07T22:20:00', 'amount': 0.0, 'unit': 'U'}, iob[0])
        self.assertDictEqual({'date': '2015-09-08T02:35:00', 'amount': 0.0, 'unit': 'U'}, iob[-1])

    def test_complicated_history(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        effect = calculate_iob(
            normalized_history,
            4,
            visual_iob_only=False
        )

        self.assertDictEqual({'date': '2015-10-15T18:05:00', 'amount': 0.0, 'unit': 'U'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-10-15T18:10:00', 'unit': 'U'}, effect[1])
        self.assertAlmostEqual(0.0, effect[1]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T18:20:00', 'unit': 'U'}, effect[3])
        self.assertAlmostEqual(-0.02, effect[3]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T19:05:00', 'unit': 'U'}, effect[12])
        self.assertAlmostEqual(-0.39, effect[12]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T20:05:00', 'unit': 'U'}, effect[24])
        self.assertAlmostEqual(5.61, effect[24]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T21:05:00', 'unit': 'U'}, effect[36])
        self.assertAlmostEqual(6.92, effect[36]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-16T02:40:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(0, effect[-1]['amount'], delta=0.01)

    def test_complicated_history_visual_iob_true(self):
        with open(get_file_at_path('fixtures/normalize_history.json')) as fp:
            history = json.load(fp)

        with open(get_file_at_path('fixtures/iob.json')) as fp:
            expected_output = json.load(fp)

        self.assertListEqual(expected_output, calculate_iob(history, 4))

    def test_start_at(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        effect = calculate_iob(
            normalized_history,
            4,
            start_at=datetime(2015, 10, 15, 22, 11, 00),
            visual_iob_only=False
        )

        self.assertDictContainsSubset({'date': '2015-10-15T22:11:00', 'unit': 'U'}, effect[0])
        self.assertAlmostEqual(7.73, effect[0]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-16T02:41:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(0, effect[-1]['amount'], delta=0.01)

    def test_end_at(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        effect = calculate_iob(
            normalized_history,
            4,
            end_at=datetime(2015, 10, 15, 20, 16, 00),
            visual_iob_only=True
        )

        self.assertDictEqual({'date': '2015-10-15T18:05:00', 'amount': 0.0, 'unit': 'U'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-10-15T18:10:00', 'unit': 'U'}, effect[1])
        self.assertAlmostEqual(-0.02, effect[1]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T18:20:00', 'unit': 'U'}, effect[3])
        self.assertAlmostEqual(-0.15, effect[3]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T19:05:00', 'unit': 'U'}, effect[12])
        self.assertAlmostEqual(-0.46, effect[12]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T20:15:00', 'unit': 'U'}, effect[-2])
        self.assertAlmostEqual(9.27, effect[-2]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T20:20:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(9.13, effect[-1]['amount'], delta=0.01)

        effect = calculate_iob(
            normalized_history,
            4,
            end_at=datetime(2015, 10, 15, 20, 16, 00),
            visual_iob_only=False
        )

        self.assertDictEqual({'date': '2015-10-15T18:05:00', 'amount': 0.0, 'unit': 'U'}, effect[0])
        self.assertDictContainsSubset({'date': '2015-10-15T18:10:00', 'unit': 'U'}, effect[1])
        self.assertAlmostEqual(0.0, effect[1]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T18:20:00', 'unit': 'U'}, effect[3])
        self.assertAlmostEqual(-0.02, effect[3]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T19:05:00', 'unit': 'U'}, effect[12])
        self.assertAlmostEqual(-0.39, effect[12]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T20:15:00', 'unit': 'U'}, effect[-2])
        self.assertAlmostEqual(5.86, effect[-2]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-15T20:20:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(9.10, effect[-1]['amount'], delta=0.01)

    def test_start_at_end_at(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        effect = calculate_iob(
            normalized_history,
            4,
            start_at=datetime(2015, 10, 15, 22, 11, 00),
            end_at=datetime(2015, 10, 16, 00, 01, 50),
            visual_iob_only=False
        )

        self.assertDictContainsSubset({'date': '2015-10-15T22:11:00', 'unit': 'U'}, effect[0])
        self.assertAlmostEqual(7.73, effect[0]['amount'], delta=0.01)
        self.assertDictContainsSubset({'date': '2015-10-16T00:06:00', 'unit': 'U'}, effect[-1])
        self.assertAlmostEqual(2.16, effect[-1]['amount'], delta=0.01)

    def test_single_entry(self):
        with open(get_file_at_path("fixtures/normalize_history.json")) as fp:
            normalized_history = json.load(fp)

        effect = calculate_iob(
            normalized_history,
            4,
            start_at=datetime(2015, 10, 15, 22, 11, 00),
            end_at=datetime(2015, 10, 15, 22, 11, 00),
            visual_iob_only=False
        )

        self.assertListEqual(
            [{
                'date': '2015-10-15T22:11:00',
                'unit': 'U',
                'amount': 7.729
            }],
            [e.update({'amount': round(e['amount'], 3)}) or e for e in effect]
        )

    def test_reservoir_history(self):
        with open(get_file_at_path('fixtures/normalized_reservoir_history_output.json')) as fp:
            normalized_history = json.load(fp)
        with open(get_file_at_path('fixtures/iob_from_reservoir_output.json')) as fp:
            expected_output = json.load(fp)

        effect = calculate_iob(normalized_history, 4)

        self.assertListEqual(expected_output, effect)


class CalculateGlucoseFromEffectsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(get_file_at_path('fixtures/glucose_from_effects_carb_effect_input.json')) as fp:
            cls.carb_effect = json.load(fp)

        with open(get_file_at_path('fixtures/glucose_from_effects_insulin_effect_input.json')) as fp:
            cls.insulin_effect = json.load(fp)

        with open(get_file_at_path('fixtures/glucose_from_effects_glucose_input.json')) as fp:
            cls.glucose = json.load(fp)

    def test_carb_and_insulin(self):
        glucose = calculate_glucose_from_effects([self.carb_effect, self.insulin_effect], self.glucose)

        with open(get_file_at_path('fixtures/glucose_from_effects_no_momentum_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)

    def test_momentum_empty(self):
        glucose = calculate_glucose_from_effects([self.carb_effect, self.insulin_effect], self.glucose, momentum=[])

        with open(get_file_at_path('fixtures/glucose_from_effects_no_momentum_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)

    def test_momentum_flat(self):
        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_flat_input.json')) as fp:
            momentum = json.load(fp)

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_flat_glucose_input.json')) as fp:
            glucose = json.load(fp)

        glucose = calculate_glucose_from_effects(
            [self.carb_effect, self.insulin_effect],
            glucose,
            momentum=momentum
        )

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_flat_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)

    def test_momentum_up(self):
        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_up_input.json')) as fp:
            momentum = json.load(fp)

        glucose = calculate_glucose_from_effects(
            [self.carb_effect, self.insulin_effect],
            self.glucose,
            momentum=momentum
        )

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_up_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)

    def test_momentum_down(self):
        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_down_input.json')) as fp:
            momentum = json.load(fp)

        glucose = calculate_glucose_from_effects(
            [self.carb_effect, self.insulin_effect],
            self.glucose,
            momentum=momentum
        )

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_down_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)

    def test_momentum_blend(self):
        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_blend_insulin_effect_input.json')) as fp:
            insulin_effect = json.load(fp)

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_blend_glucose_input.json')) as fp:
            glucose = json.load(fp)

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_blend_momentum_input.json')) as fp:
            momentum = json.load(fp)

        glucose = calculate_glucose_from_effects([insulin_effect], glucose, momentum=momentum)

        with open(get_file_at_path('fixtures/glucose_from_effects_momentum_blend_output.json')) as fp:
            output = json.load(fp)

        self.assertListEqual(output, glucose)


class CalculateMomentumEffectTestCase(unittest.TestCase):
    def test_rising_glucose(self):
        with open(get_file_at_path('fixtures/momentum_effect_rising_glucose_input.json')) as fp:
            glucose = json.load(fp)

        with open(get_file_at_path('fixtures/momentum_effect_rising_glucose_output.json')) as fp:
            output = json.load(fp)

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual(output, momentum)

    def test_bouncing_glucose(self):
        with open(get_file_at_path('fixtures/momentum_effect_bouncing_glucose_input.json')) as fp:
            glucose = json.load(fp)

        with open(get_file_at_path('fixtures/momentum_effect_bouncing_glucose_output.json')) as fp:
            output = json.load(fp)

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual(output, momentum)

    def test_falling_glucose(self):
        with open(get_file_at_path('fixtures/momentum_effect_falling_glucose_input.json')) as fp:
            glucose = json.load(fp)

        with open(get_file_at_path('fixtures/momentum_effect_falling_glucose_output.json')) as fp:
            output = json.load(fp)

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual(output, momentum)

    def test_stable_glucose(self):
        with open(get_file_at_path('fixtures/momentum_effect_stable_glucose_input.json')) as fp:
            glucose = json.load(fp)

        with open(get_file_at_path('fixtures/momentum_effect_stable_glucose_output.json')) as fp:
            output = json.load(fp)

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual(output, momentum)

    def test_missing_number_of_entries(self):
        glucose = [
            {
                'date': '2015-10-25T19:30:00',
                'amount': 120
            },
            {
                'date': '2015-10-25T19:25:00',
                'amount': 120
            }
        ]

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual([], momentum)

    def test_missing_range_of_entries(self):
        glucose = [
            {
                'date': '2015-10-25T19:30:00',
                'amount': 120
            },
            {
                'date': '2015-10-25T19:20:00',
                'amount': 120
            },
            {
                'date': '2015-10-25T19:14:59',
                'amount': 120
            },
            {
                'date': '2015-10-25T19:10:00',
                'amount': 123
            }
        ]

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual([], momentum)

    def test_recent_calibrations(self):
        with open(get_file_at_path('fixtures/cgms_calibrations.json')) as fp:
            calibrations = json.load(fp)

        glucose = [
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:16:47",
                "display_time": "2015-10-27T17:17:38",
                "glucose": 147
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:16:47",
                "display_time": "2015-10-27T17:17:38",
                "glucose": 153
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:11:46",
                "display_time": "2015-10-27T17:12:37",
                "glucose": 146
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:06:45",
                "display_time": "2015-10-27T17:07:37",
                "glucose": 148
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:01:46",
                "display_time": "2015-10-27T17:02:38",
                "glucose": 149
            }
        ]

        momentum = calculate_momentum_effect(glucose, recent_calibrations=calibrations)

        self.assertListEqual([], momentum)

    def test_timestamp_rounding(self):
        glucose = [
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:16:47",
                "display_time": "2015-10-27T17:17:38",
                "glucose": 153
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:11:46",
                "display_time": "2015-10-27T17:12:37",
                "glucose": 146
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:06:45",
                "display_time": "2015-10-27T17:07:37",
                "glucose": 148
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-28T01:01:46",
                "display_time": "2015-10-27T17:02:38",
                "glucose": 149
            }
        ]

        momentum = calculate_momentum_effect(glucose)

        self.assertListEqual([
            {
                'date': '2015-10-27T17:15:00',
                'amount': 0,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:20:00',
                'amount': 1.18,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:25:00',
                'amount': 3.68,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:30:00',
                'amount': 6.18,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:35:00',
                'amount': 8.68,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:40:00',
                'amount': 11.18,
                'unit': 'mg/dL'
            },
            {
                'date': '2015-10-27T17:45:00',
                'amount': 13.67,
                'unit': 'mg/dL'
            }
        ], [{'date': m['date'], 'unit': m['unit'], 'amount': round(m['amount'], 2)} for m in momentum])

    def test_prediction_time(self):
        glucose = [
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-30T17:16:36",
                "display_time": "2015-10-30T09:17:27",
                "glucose": 111
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-30T17:11:36",
                "display_time": "2015-10-30T09:12:27",
                "glucose": 111
            },
            {
                "trend_arrow": "FLAT",
                "system_time": "2015-10-30T17:06:36",
                "display_time": "2015-10-30T09:07:28",
                "glucose": 113
            }
        ]

        momentum = calculate_momentum_effect(recent_glucose=glucose, prediction_time=20)

        self.assertListEqual(
            [
                {'amount': -0.00, 'date': '2015-10-30T09:15:00', 'unit': 'mg/dL'},
                {'amount': -0.51, 'date': '2015-10-30T09:20:00', 'unit': 'mg/dL'},
                {'amount': -1.51, 'date': '2015-10-30T09:25:00', 'unit': 'mg/dL'},
                {'amount': -2.51, 'date': '2015-10-30T09:30:00', 'unit': 'mg/dL'},
                {'amount': -3.51, 'date': '2015-10-30T09:35:00', 'unit': 'mg/dL'}
            ],
            [{'date': m['date'], 'unit': m['unit'], 'amount': round(m['amount'], 2)} for m in momentum]
        )
