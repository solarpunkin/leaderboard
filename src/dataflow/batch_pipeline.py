import argparse
import json
import logging

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
import redis
import pyarrow

# Define a custom DoFn for safe parsing and dead-lettering
class SafeParseJson(beam.DoFn):
    DEAD_LETTER_TAG = 'dead_letter'

    def process(self, element):
        try:
            # The element from ReadFromPubSub is a PubsubMessage object.
            # The data is directly available as bytes.
            msg_value = element.decode('utf-8')
            data = json.loads(msg_value)
            if 'event_id' in data:
                yield data # Success, yield to main output
            else:
                # The JSON is valid, but missing the required key.
                yield beam.pvalue.TaggedOutput(self.DEAD_LETTER_TAG, msg_value)

        except Exception as e:
            # If ANY exception occurs, log it and dead-letter the original record.
            logging.error(f"Failed to parse element. Error: {e} | Element Type: {type(element)}")
            yield beam.pvalue.TaggedOutput(self.DEAD_LETTER_TAG, str(element))

class WriteToRedisDoFn(beam.DoFn):
    def __init__(self, redis_host, redis_port):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None

    def setup(self):
        self.redis_client = redis.Redis(
            host=self.redis_host, port=self.redis_port, decode_responses=True, ssl=True, ssl_cert_reqs=None
        )

    def process(self, batch, window=beam.DoFn.WindowParam):
        try:
            # Format the window end time into a string like "leaderboard:2025-11-18-14"
            hour_key = window.end.to_utc_datetime().strftime("leaderboard:%Y-%m-%d-%H")
            
            pipe = self.redis_client.pipeline()
            for event_id, count in batch:
                # Write to the key for that specific hour
                pipe.zadd(hour_key, {event_id: count}, incr=True)
            # Set an expiry on the key so old data is automatically deleted after a week
            pipe.expire(hour_key, 3600 * 24 * 7)
            pipe.execute()
        except Exception as e:
            logging.error(f"Failed to write batch of size {len(batch)} to Redis: {e}")

# Define custom pipeline options
class LeaderboardPipelineOptions(PipelineOptions):
    @classmethod
    def _add_argparse_args(cls, parser):
        parser.add_argument("--gcp_project_id", required=True)
        parser.add_argument("--pubsub_subscription", required=True)
        parser.add_argument("--redis_host", required=True)
        parser.add_argument("--redis_port", required=True, type=int)
        parser.add_argument("--dead_letter_gcs_path", required=True)
        parser.add_argument("--archive_gcs_path", required=True)

def run(argv=None):
    pipeline_options = PipelineOptions(argv)
    custom_options = pipeline_options.view_as(LeaderboardPipelineOptions)

    with beam.Pipeline(options=pipeline_options) as pipeline:
        subscription_name = f"projects/{custom_options.gcp_project_id}/subscriptions/{custom_options.pubsub_subscription}"
        pubsub_messages = pipeline | "ReadFromPubSub" >> beam.io.ReadFromPubSub(subscription=subscription_name)

        parsed_results = pubsub_messages | 'SafeParse' >> beam.ParDo(SafeParseJson()).with_outputs(
            SafeParseJson.DEAD_LETTER_TAG, main='main'
        )

        good_records = parsed_results.main
        dead_letter_records = parsed_results[SafeParseJson.DEAD_LETTER_TAG]

        (   good_records
            | "ApplyHourlyWindow" >> beam.WindowInto(
                beam.window.FixedWindows(3600),
                trigger=beam.trigger.AfterWatermark(
                    early=beam.trigger.Repeatedly(beam.trigger.AfterProcessingTime(60))
                ),
                accumulation_mode=beam.trigger.AccumulationMode.ACCUMULATING
            )
            | "ExtractEventID" >> beam.Map(lambda msg: msg["event_id"])
            | "CountEvents" >> beam.combiners.Count.PerElement()
            | "BatchElements" >> beam.BatchElements(min_batch_size=100, max_batch_size=1000)
            | "WriteToRedis" >> beam.ParDo(
                WriteToRedisDoFn(
                    redis_host=custom_options.redis_host, redis_port=custom_options.redis_port
                )
            )
        )

        (   dead_letter_records
            | 'WindowDeadLetter' >> beam.WindowInto(beam.window.FixedWindows(300))
            | 'FormatDeadLetter' >> beam.Map(lambda x: str(x))
            | 'WriteDeadLetterToGCS' >> beam.io.WriteToText(custom_options.dead_letter_gcs_path)
        )

        (   good_records  # This is the same PCollection of parsed JSON messages
            | "Window for Archiving" >> beam.WindowInto(beam.window.FixedWindows(300)) # 5-minute files
            | "Write to Parquet" >> beam.io.WriteToParquet(
                file_path_prefix=custom_options.archive_gcs_path,
                file_name_suffix=".parquet",
                # Define the schema for the Parquet file based on your JSON.
                # This ensures the data is strongly typed for BigQuery.
                schema=pyarrow.schema([
                    pyarrow.field('event_id', pyarrow.string())
                    # If you add a timestamp to your events, define it here too:
                    # pyarrow.field('timestamp', pyarrow.timestamp('ns')),
                ])
            )
        )

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
