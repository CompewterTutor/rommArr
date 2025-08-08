#!/bin/bash
# trunk-ignore-all(shellcheck/SC2016)

set -e

echo "Starting entrypoint script..."

# Create symlinks for frontend
for subfolder in assets resources; do
	if [[ -L /app/frontend/assets/romm/${subfolder} ]]; then
		target=$(readlink "/app/frontend/assets/romm/${subfolder}")

		# If the target is not the same as ${ROMM_BASE_PATH}/${subfolder}, recreate the symbolic link.
		if [[ ${target} != "${ROMM_BASE_PATH}/${subfolder}" ]]; then
			rm "/app/frontend/assets/romm/${subfolder}"
			ln -s "${ROMM_BASE_PATH}/${subfolder}" "/app/frontend/assets/romm/${subfolder}"
		fi
	elif [[ ! -e /app/frontend/assets/romm/${subfolder} ]]; then
		# Ensure parent directory exists before creating symbolic link
		mkdir -p "/app/frontend/assets/romm"
		ln -s "${ROMM_BASE_PATH}/${subfolder}" "/app/frontend/assets/romm/${subfolder}"
	fi
done

# Define a signal handler to propagate termination signals
function handle_termination() {
	echo "Terminating child processes..."
	# Kill all background jobs
	# trunk-ignore(shellcheck)
	kill -TERM $(jobs -p) 2>/dev/null
}

# Trap SIGTERM and SIGINT signals
trap handle_termination SIGTERM SIGINT

# Start all services in the background
echo "Starting backend..."
cd /app/backend
uv run python main.py &

echo "Starting RQ scheduler..."
RQ_REDIS_HOST=${REDIS_HOST:-127.0.0.1} \
	RQ_REDIS_PORT=${REDIS_PORT:-6379} \
	RQ_REDIS_USERNAME=${REDIS_USERNAME:-""} \
	RQ_REDIS_PASSWORD=${REDIS_PASSWORD:-""} \
	RQ_REDIS_DB=${REDIS_DB:-0} \
	RQ_REDIS_SSL=${REDIS_SSL:-0} \
	rqscheduler \
	--path /app/backend \
	--pid /tmp/rq_scheduler.pid &

echo "Starting RQ worker..."
# Build Redis URL properly
if [[ -n ${REDIS_PASSWORD-} ]]; then
	REDIS_URL="redis${REDIS_SSL:+s}://${REDIS_USERNAME-}:${REDIS_PASSWORD}@${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}/${REDIS_DB:-0}"
elif [[ -n ${REDIS_USERNAME-} ]]; then
	REDIS_URL="redis${REDIS_SSL:+s}://${REDIS_USERNAME}@${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}/${REDIS_DB:-0}"
else
	REDIS_URL="redis${REDIS_SSL:+s}://${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}/${REDIS_DB:-0}"
fi

# Set PYTHONPATH so RQ can find the tasks module
PYTHONPATH="/app/backend:${PYTHONPATH-}" rq worker \
	--path /app/backend \
	--pid /tmp/rq_worker.pid \
	--url "${REDIS_URL}" \
	high default low &

echo "Starting watcher..."
watchfiles \
	--target-type command \
	'uv run python watcher.py' \
	/app/romm/library &

echo "Starting ps3netsrv..."
# Create ps3netsrv directory structure with symbolic links
PS3NETSRV_ROOT="/app/romm/library/ps3netsrv"
mkdir -p "${PS3NETSRV_ROOT}"

# Create symbolic links for ps3netsrv expected folder structure
if [[ -d "/app/romm/library/roms/ps3" ]]; then
	ln -sf "/app/romm/library/roms/ps3" "${PS3NETSRV_ROOT}/GAMES"
fi

# Start ps3netsrv with the prepared directory
ps3netsrv "${PS3NETSRV_ROOT}" 38008 * &

# Start the frontend dev server
cd /app/frontend
npm run dev &

# Wait for all background processes
wait
