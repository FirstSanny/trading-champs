#!/bin/bash
# Monitor deployment status and verify watchlist symbols after deploy
# Usage: ./scripts/monitor_deploy.sh

PROJECT_ID="prj_jPOWBQnZxJdRA9OSQRBYPs5G5i1t"
COMMIT_SHA="d7f7766"
POLL_INTERVAL=10
MAX_WAIT=300

echo "=========================================="
echo "Deployment Monitor - trading-champs"
echo "=========================================="
echo "Waiting for commit: $COMMIT_SHA"
echo ""

# Get current deployment state
get_deployment_state() {
    curl -s "https://api.vercel.com/v1/projects/$PROJECT_ID" \
        -H "Authorization: Bearer $VERCEL_ACCESS_TOKEN" | \
        jq '.latestDeployments[0] | {sha: .meta.gitCommitSha, state: .readyState, created: .createdAt}'
}

# Poll for deployment
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    state=$(get_deployment_state)
    current_sha=$(echo "$state" | jq -r '.sha')
    ready_state=$(echo "$state" | jq -r '.state')
    created=$(echo "$state" | jq -r '.created')
    
    echo "[$(date +%H:%M:%S)] State: $ready_state | Commit: ${current_sha:0:8}..."
    
    if [ "$ready_state" = "READY" ]; then
        if [ "$current_sha" = "$COMMIT_SHA" ] || [ "$current_sha" = "${COMMIT_SHA:0:8}" ]; then
            echo ""
            echo "✅ Deployment complete with correct commit!"
            echo ""
            echo "Checking watchlist symbols..."
            
            # Query Supabase for new symbols
            echo ""
            echo "📈 New Stocks:"
            curl -s "https://ivqyvyweiiyrbosvwkjq.supabase.co/rest/v1/watchlist_symbols?enabled=eq.true&select=symbol,asset_class&added_by=ilike.seed" \
                -H "apikey: sb_publishable_iFyl77YCPxtti-CVP-VE_w_H7k19iIm" \
                -H "Authorization: Bearer sb_publishable_iFyl77YCPxtti-CVP-VE_w_H7k19iIm" | \
                jq -r '.[] | "\(.symbol) (\(.asset_class))"'
            
            echo ""
            echo "✅ Done!"
            exit 0
        else
            echo "⚠️  Deployment ready but different commit: ${current_sha:0:8}"
        fi
    fi
    
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo ""
echo "❌ Timeout waiting for deployment"
exit 1
