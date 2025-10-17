1. Build and Push the Multi-arch Image:

   1     # Make sure you are in the root directory of the 'leaderboard' project
   2     docker buildx build \
   3       --platform linux/amd64,linux/arm64 \
   4       -t gcr.io/aftermath-69/leaderboard:latest \
   5       --push .

   2. Restart the API Deployment:
   1     kubectl rollout restart deployment leaderboard-api

  ---

  How to Use Your Leaderboard

  Here is a step-by-step guide to interacting with the different parts of your system.

  1. See Events Being Published

  The event-publisher service is continuously running and creating new events. You can watch its logs to see the event IDs it's 
  publishing. You will need some of these IDs for the next step.

   1 # Get the name of the event-publisher pod
   2 PUBLISHER_POD=$(kubectl get pods -l app=event-publisher -o jsonpath='{.items[0].metadata.name}')
   3 
   4 # Watch the logs
   5 kubectl logs -f $PUBLISHER_POD
  You will see output like this. Keep a few of the UUIDs handy.

   1 Published event 9c938099-9e9e-45fe-b8ee-0775c58ff041 to topic leaderboard_events
   2 Published event fa2b2b5d-74ee-40f7-9ca1-772ad64bf973 to topic leaderboard_events
   3 ...

  2. Get Approximate Results (Real-time)

  This query uses the Count-Min Sketch that is updated in real-time by the realtime-processor. It gives you a very fast but 
  approximate count for specific event IDs.

   1. Get the API's External IP:

   1     export API_IP=$(kubectl get service leaderboard-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
   2     echo "API IP Address: $API_IP"

   2. Query the `/approximate` endpoint:
      Take some of the event IDs you saw in the publisher logs and use them in the command below.

   1     # Replace with your actual event IDs, separated by commas
   2     EVENT_IDS="9c938099-9e9e-45fe-b8ee-0775c58ff041,fa2b2b5d-74ee-40f7-9ca1-772ad64bf973"
   3 
   4     curl "http://$API_IP/leaderboard/approximate?event_ids=$EVENT_IDS"
      The output will be a JSON object with the estimated counts for each event.

  3. Get Exact Top-K Results (Batch)

  This query uses the data from the hourly batch-processor job. It is 100% accurate but only as recent as the last completed batch.

   1. Manually Trigger the Batch Job:
      To get results without waiting an hour, manually trigger the batch job.

   1     kubectl create job --from=cronjob/batch-processor manual-batch-1
      Wait about a minute for the job to complete.

   2. Query the `/leaderboard` endpoint:
      Now query the main endpoint to get the exact top-K list from the batch data.

   1     curl "http://$API_IP/leaderboard?k=5"
      The output will be a JSON array of the top 5 events and their exact counts from the batch.

