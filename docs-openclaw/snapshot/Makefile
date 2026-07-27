.PHONY: build up down logs demo demo-sverk demo-painters demo-painters-sverk \
        demo-studio up-painters down-painters demo-survey demo-city headless \
        demo-distributed hub drone down-distributed verdict clean reset \
        local local-painters local-debate local-collab local-studio \
        local-survey local-city local-city-gazebo local-test3x3 web stop-local pause resume \
        pause-docker resume-docker deploy-fleet \
        payments-demo payments-test payments-down demo-survey-commerce \
        down-survey-commerce ton-jton-bootstrap payments-ton-demo \
        payments-ton-test payments-ton-down demo-survey-commerce-ton \
        demo-hackathon down-hackathon lan-urls mission-rerun \
        payments-client payments-client-down

# --- деплой ноды на ФЛОТ реальных дронов (см. deploy/ansible/README.md) ---
deploy-fleet:
	ansible-playbook -i deploy/ansible/inventory.yml deploy/ansible/deploy.yml

PAYMENTS_COMPOSE = docker compose -f docker-compose.payments.yml
PAYMENTS_TEST_COMPOSE = $(PAYMENTS_COMPOSE) -f docker-compose.payments.test.yml
SURVEY_COMMERCE_COMPOSE = docker compose -f docker-compose.yml \
	-f docker-compose.payments.yml -f docker-compose.survey-commerce.yml
PAYMENTS_TON_COMPOSE = docker compose --env-file .env.ton \
	-f docker-compose.payments.ton.yml
SURVEY_COMMERCE_TON_COMPOSE = docker compose --env-file .env.ton \
	-f docker-compose.yml -f docker-compose.payments.ton.yml \
	-f docker-compose.survey-commerce.yml
HACKATHON_COMPOSE = $(SURVEY_COMMERCE_COMPOSE) -f docker-compose.lan.yml
# The LAN the demo is published on is the WIFI the participants join — NOT the
# default route. On this host the default route is the ethernet uplink that
# carries internet, and a VPN can own it too; both answers are useless to a
# laptop on the wifi. So resolve the wireless device explicitly and read its
# address. Override either value by hand when the guess is wrong:
#   make demo-hackathon LAN_IFACE=wlan0
#   make demo-hackathon LAN_IP=192.168.1.150
LAN_IFACE ?= $(shell nmcli -t -f DEVICE,TYPE con show --active 2>/dev/null \
	| awk -F: '$$2=="802-11-wireless"{print $$1;exit}')
LAN_IP ?= $(shell ip -4 -o addr show $(LAN_IFACE) 2>/dev/null \
	| grep -oP 'inet \K[^/]+' | head -1)
# Services listen on the wifi address only, so the ethernet uplink never sees
# the unauthenticated anvil RPC. Exported for docker-compose.lan.yml.
LAN_BIND_IP ?= $(LAN_IP)
export LAN_BIND_IP

payments-demo:
	-$(PAYMENTS_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(PAYMENTS_COMPOSE) build payment-bootstrap
	$(PAYMENTS_COMPOSE) up --no-build -d --wait commerce-runtime payment-explorer
	$(PAYMENTS_COMPOSE) run --no-deps --rm demo-driver
	@echo "payment explorer: http://localhost:8090"
	@echo "commerce API: http://localhost:8081"

payments-test:
	-$(PAYMENTS_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(PAYMENTS_COMPOSE) build payment-bootstrap
	$(PAYMENTS_COMPOSE) up -d --wait anvil
	$(PAYMENTS_COMPOSE) up -d --wait payment-bootstrap
	$(PAYMENTS_TEST_COMPOSE) run --rm commerce-runtime python -m unittest discover -s payments/tests -p 'test_*.py'
	$(PAYMENTS_TEST_COMPOSE) run --rm commerce-runtime python -m unittest discover -s tests -p 'test_*.py'

payments-down:
	$(PAYMENTS_COMPOSE) down -v --remove-orphans

# --- participant mode: no local chain, join the shared node ---
# PAYMENTS_RPC_URL and PAYMENTS_DEPLOYER_PRIVATE_KEY are mandatory; compose
# fails with a readable message when either is missing.
PAYMENTS_CLIENT_COMPOSE = $(PAYMENTS_COMPOSE) -f docker-compose.payments.client.yml
payments-client:
	$(PAYMENTS_CLIENT_COMPOSE) build payment-bootstrap
	$(PAYMENTS_CLIENT_COMPOSE) up --no-build -d --wait commerce-runtime payment-explorer
	$(PAYMENTS_CLIENT_COMPOSE) run --no-deps --rm demo-driver
	@echo "payment explorer: http://localhost:8090   (chain: $(PAYMENTS_RPC_URL))"
	@echo "commerce API:     http://localhost:8081/docs"

payments-client-down:
	$(PAYMENTS_CLIENT_COMPOSE) down -v --remove-orphans

ton-jton-bootstrap:
	@test -f .env.ton || { echo "missing .env.ton (copy .env.ton.example)"; exit 1; }
	docker build -f Dockerfile.ton-contracts -t archipelago-jton-contracts:local .
	docker build -f Dockerfile.payments -t archipelago-payments:local .
	docker run --rm --env-file .env.ton -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m payments.ton_operator fund-admin
	docker run --rm --env-file .env.ton -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m payments.ton_operator preflight
	@mkdir -p .ton-bootstrap
	docker run --rm --env-file .env.ton \
	  -e WALLET_VERSION=v5r1 -e SUBWALLET_NUMBER=1000 \
	  -v "$$(pwd)/.ton-bootstrap:/out" \
	  archipelago-jton-contracts:local \
	  sh -lc 'export WALLET_MNEMONIC="$$TON_DEMO_MNEMONIC"; \
	    npx blueprint run deployJton --testnet --mnemonic'
	docker run --rm -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m payments.ton_operator \
	  update-master --address-file .ton-bootstrap/JTON_MASTER_ADDRESS
	@seed="$$(docker run --rm --env-file .env.ton -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m payments.ton_operator seed-json)"; \
	docker run --rm --env-file .env.ton \
	  -e WALLET_VERSION=v5r1 -e SUBWALLET_NUMBER=1000 \
	  -e JTON_SEED_JSON="$$seed" \
	  archipelago-jton-contracts:local \
	  sh -lc 'export WALLET_MNEMONIC="$$TON_DEMO_MNEMONIC"; \
	    npx blueprint run seedJton --testnet --mnemonic'

payments-ton-demo: ton-jton-bootstrap
	-$(PAYMENTS_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	-$(PAYMENTS_TON_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(PAYMENTS_TON_COMPOSE) build ton-payment-bootstrap
	$(PAYMENTS_TON_COMPOSE) up --no-build -d --wait commerce-runtime payment-explorer
	$(PAYMENTS_TON_COMPOSE) run --no-deps --rm demo-driver
	@echo "TON payment explorer: http://localhost:8090"
	@echo "TON commerce API: http://localhost:8081"

payments-ton-test:
	docker build -f Dockerfile.ton-contracts -t archipelago-jton-contracts:local .
	docker run --rm archipelago-jton-contracts:local npm test -- --runInBand
	docker build -f Dockerfile.payments -t archipelago-payments:local .
	docker run --rm -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m unittest discover \
	  -s payments/tests -p 'test_*.py'
	docker run --rm -v "$$(pwd):/workspace" -w /workspace \
	  archipelago-payments:local python -m unittest discover \
	  -s tests -p 'test_*.py'

payments-ton-down:
	$(PAYMENTS_TON_COMPOSE) down -v --remove-orphans

demo-survey-commerce-ton: ton-jton-bootstrap
	-docker compose down -v --remove-orphans >/dev/null 2>&1
	-$(PAYMENTS_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	-$(SURVEY_COMMERCE_TON_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(SURVEY_COMMERCE_TON_COMPOSE) build coordinator bridge-drone-1 viz ton-payment-bootstrap
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(SURVEY_COMMERCE_TON_COMPOSE) up --no-build -d --wait \
	  commerce-runtime payment-explorer viz commerce-observer
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(SURVEY_COMMERCE_TON_COMPOSE) up --no-build -d \
	  coordinator drone-1 drone-2 drone-3 drone-4 rover
	PAYMENTS_DEMO_NAMESPACE=$${PAYMENTS_DEMO_NAMESPACE:-survey-commerce-ton-demo} \
	  $(SURVEY_COMMERCE_TON_COMPOSE) run --no-deps --rm demo-driver
	@echo "combined TON dashboard: http://localhost:8080/survey-commerce"
	@echo "disable widget:          http://localhost:8080/survey-commerce?commerce=0"
	@echo "TON payment explorer:    http://localhost:8090"
	@echo "TON commerce API:        http://localhost:8081/docs"
	@DC="$(SURVEY_COMMERCE_TON_COMPOSE)" TIMEOUT=$${TIMEOUT:-360} bash scripts/wait_done.sh

demo-survey-commerce:
	-docker compose down -v --remove-orphans >/dev/null 2>&1
	-$(SURVEY_COMMERCE_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(SURVEY_COMMERCE_COMPOSE) build coordinator bridge-drone-1 viz payment-bootstrap
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(SURVEY_COMMERCE_COMPOSE) up --no-build -d --wait \
	  commerce-runtime payment-explorer viz commerce-observer
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(SURVEY_COMMERCE_COMPOSE) up --no-build -d \
	  coordinator drone-1 drone-2 drone-3 drone-4 rover
	PAYMENTS_DEMO_NAMESPACE=$${PAYMENTS_DEMO_NAMESPACE:-survey-commerce-demo} \
	  $(SURVEY_COMMERCE_COMPOSE) run --no-deps --rm demo-driver
	@echo "combined dashboard: http://localhost:8095/survey-commerce"
	@echo "disable widget:     http://localhost:8095/survey-commerce?commerce=0"
	@echo "payment explorer:   http://localhost:8090"
	@echo "commerce API:       http://localhost:8081/docs"
	@DC="$(SURVEY_COMMERCE_COMPOSE)" TIMEOUT=$${TIMEOUT:-360} bash scripts/wait_done.sh

down-survey-commerce:
	$(SURVEY_COMMERCE_COMPOSE) down -v --remove-orphans

# --- hackathon floor: one host serves the chain and both dashboards ---
# Same stack as demo-survey-commerce, but every port is republished on 0.0.0.0
# and anvil runs the canonical test mnemonic so participants have funded keys.
# See docker-compose.lan.yml for the trust caveat.
demo-hackathon:
	@test -n "$(LAN_IP)" || { echo "no address on wifi device '$(LAN_IFACE)' — pass LAN_IFACE=<dev> or LAN_IP=<ip>"; exit 1; }
	-docker compose down -v --remove-orphans >/dev/null 2>&1
	-$(HACKATHON_COMPOSE) down -v --remove-orphans >/dev/null 2>&1
	$(HACKATHON_COMPOSE) build coordinator bridge-drone-1 viz payment-bootstrap
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(HACKATHON_COMPOSE) up --no-build -d --wait \
	  commerce-runtime payment-explorer viz commerce-observer
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(HACKATHON_COMPOSE) $(if $(EGRESS),-f docker-compose.egress.yml,) \
	  up --no-build -d \
	  coordinator drone-1 drone-2 drone-3 drone-4 rover
	PAYMENTS_DEMO_NAMESPACE=$${PAYMENTS_DEMO_NAMESPACE:-hackathon-demo} \
	  $(HACKATHON_COMPOSE) run --no-deps --rm demo-driver
	@$(MAKE) --no-print-directory lan-urls

lan-urls:
	@echo "publishing on $(LAN_IFACE) ($(LAN_IP)) — uplink not exposed"
	@echo "mission dashboard: http://$(LAN_IP):$${VIZ_HOST_PORT:-8095}/survey-commerce"
	@echo "crypto dashboard:  http://$(LAN_IP):8090"
	@echo "commerce API:      http://$(LAN_IP):8081/docs"
	@echo "shared RPC:        http://$(LAN_IP):8545   chainId 31337"

# Re-run the MISSION only, leaving anvil / the dashboards / the deployed token
# untouched. `demo-hackathon` opens with `down -v`, which wipes the chain volume:
# every participant's MetaMask nonce and the token address die with it. So once
# the floor is live, replay runs through here instead.
#
# MODEL_PROVIDER=sverk (or any real brain) additionally needs the egress overlay:
# agents sit on the `mesh` network, which is internal:true, so without it the LLM
# call cannot leave the container and the agents quietly fall back to templates.
#   make mission-rerun EGRESS=1
MISSION_AGENTS = coordinator drone-1 drone-2 drone-3 drone-4 rover
mission-rerun:
	TASK=survey SCENARIO=$${SCENARIO:-survey-1} WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  $(HACKATHON_COMPOSE) $(if $(EGRESS),-f docker-compose.egress.yml,) \
	  up --no-build -d --force-recreate $(MISSION_AGENTS)
	@echo "mission restarted — dashboard updates live, chain untouched"
	@DC="$(HACKATHON_COMPOSE)" TIMEOUT=$${TIMEOUT:-360} bash scripts/wait_done.sh
	# The board was wiped by the coordinator, and the commerce observer reads its
	# cursor only at startup — without this restart it keeps the in-memory cursor
	# and replays nothing, so the mission dashboard shows "0 transactions".
	$(HACKATHON_COMPOSE) up --no-build -d --force-recreate commerce-observer
	PAYMENTS_DEMO_NAMESPACE=$${PAYMENTS_DEMO_NAMESPACE:-rerun-$$(date +%H%M%S)} \
	  $(HACKATHON_COMPOSE) run --no-deps --rm demo-driver
	@$(MAKE) --no-print-directory lan-urls

down-hackathon:
	$(HACKATHON_COMPOSE) down -v --remove-orphans

# Every demo starts from a CLEAN blackboard. `make demo` wiped nothing before,
# so a persisted Docker volume replayed the previous run (old phase=DONE + old
# messages) and the agents looked like they had "already talked". `reset` drops
# the named volume so each run starts fresh; the demo targets depend on it.
reset:
	-docker compose down -v >/dev/null 2>&1
	@echo "blackboard volume cleared — next run starts fresh"

# Bring the whole stack up in the background (fresh blackboard each time).
up: reset
	docker compose up --build -d
	@echo "dashboard: http://localhost:8080"

# Sample-scenario demo: clean, build, run unattended, wait for the PASS verdict.
demo: up
	@echo "dashboard: http://localhost:8080"
	@bash scripts/wait_done.sh

# Same demo, but with the REAL sverk/qwen brain (needs .env + egress override).
# Agents narrate their reasoning via the LLM; protocol still drives actions.
demo-sverk: reset
	MODEL_PROVIDER=sverk docker compose -f docker-compose.yml -f docker-compose.egress.yml up --build -d
	@set -a; [ -f .env ] && . ./.env; set +a; \
	echo "dashboard: http://localhost:8080  (brain: sverk/$${MODEL:-qwen35})"
	@bash scripts/wait_done.sh

# --- painters scenario (4 painter drones collaborate on one canvas) ---
# Each drone has a spray can in its own color; they negotiate a subject, split
# the canvas, and paint it. The dashboard shows their thinking + the live canvas.
# SCENARIO is forced to painters-1 on the up line so it wins over a .env that
# pins SCENARIO=scenario-1 for the street demo (shell env > compose .env file).
# Sources .env so a real MODEL_PROVIDER auto-attaches the egress overlay.
demo-painters:
	-docker compose -f docker-compose.painters.yml down -v >/dev/null 2>&1
	@set -a; [ -f .env ] && . ./.env; set +a; \
	files="-f docker-compose.painters.yml"; \
	case "$${MODEL_PROVIDER:-mock}" in sverk|anthropic|openai|ollama) \
	  files="$$files -f docker-compose.painters.egress.yml";; esac; \
	SCENARIO=$${PAINTERS_SCENARIO:-painters-1} docker compose $$files up --build -d; \
	echo "painters dashboard: http://localhost:8080  (brain: $${MODEL_PROVIDER:-mock})"; \
	DC="docker compose $$files" PAINTING=1 bash scripts/wait_done.sh

demo-painters-sverk:
	-docker compose -f docker-compose.painters.yml down -v >/dev/null 2>&1
	SCENARIO=$${PAINTERS_SCENARIO:-painters-1} MODEL_PROVIDER=sverk docker compose -f docker-compose.painters.yml -f docker-compose.painters.egress.yml up --build -d
	@echo "painters dashboard: http://localhost:8080  (brain: sverk/$${MODEL:-qwen35})"
	@DC="docker compose -f docker-compose.painters.yml -f docker-compose.painters.egress.yml" PAINTING=1 bash scripts/wait_done.sh

# Containerized STUDIO (same flow as `make local-studio`): decentralized chat →
# vote → collab paint. Rerun in docker = `make demo-studio` again (down+up).
demo-studio:
	-docker compose -f docker-compose.painters.yml down -v >/dev/null 2>&1
	@set -a; [ -f .env ] && . ./.env; set +a; \
	files="-f docker-compose.painters.yml"; \
	case "$${MODEL_PROVIDER:-mock}" in sverk|anthropic|openai|ollama) \
	  files="$$files -f docker-compose.painters.egress.yml";; esac; \
	STUDIO_CHAT=1 PAINT_MODE=collab COLLAB_FREE=1 COLLAB_SHAPES=5 COLLAB_LLM_SHAPES=1 \
	  SCENARIO=$${PAINTERS_SCENARIO:-painters-1} docker compose $$files up --build -d; \
	echo "studio dashboard: http://localhost:8080/studio  (brain: $${MODEL_PROVIDER:-mock})"; \
	DC="docker compose $$files" PAINTING=1 TIMEOUT=$${TIMEOUT:-420} bash scripts/wait_done.sh

# Watch mode: same stack as demo-painters but agents stay alive after DONE so you
# can browse full thinking transcripts on the dashboard. No wait-for-DONE exit.
up-painters:
	-docker compose -f docker-compose.painters.yml down -v >/dev/null 2>&1
	@set -a; [ -f .env ] && . ./.env; set +a; \
	files="-f docker-compose.painters.yml"; \
	case "$${MODEL_PROVIDER:-mock}" in sverk|anthropic|openai|ollama) \
	  files="$$files -f docker-compose.painters.egress.yml";; esac; \
	KEEP_ALIVE=1 SCENARIO=$${PAINTERS_SCENARIO:-painters-1} docker compose $$files up --build -d; \
	echo "painters watch mode: http://localhost:8080"; \
	echo "  agents stay up after DONE — click any node for full thinking + CSV export links"

down-painters:
	-docker compose -f docker-compose.painters.yml -f docker-compose.painters.egress.yml down 2>/dev/null
	-docker compose -f docker-compose.painters.yml down 2>/dev/null
	@echo "painters stack stopped"

# --- survey scenario (город дронов v2: поиск груза на поле 5×5) ---
# 4 дрона делят поле в чате, ходами (JSON-план: fly_to → wait → photo_analyze)
# облетают клетки, находку перепроверяют ПО ОЧЕРЕДИ; кворум подтверждает —
# ровер едет к грузу. Дашборд: http://localhost:8080/survey
demo-survey:
	-docker compose down -v >/dev/null 2>&1
	@set -a; [ -f .env ] && . ./.env; set +a; \
	files="-f docker-compose.yml"; \
	case "$${MODEL_PROVIDER:-mock}" in sverk|anthropic|openai|ollama) \
	  files="$$files -f docker-compose.egress.yml";; esac; \
	TASK=survey SCENARIO=survey-1 WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  docker compose $$files up --build -d; \
	echo "survey dashboard: http://localhost:8080/survey  (brain: $${MODEL_PROVIDER:-mock})"; \
	DC="docker compose $$files" TIMEOUT=$${TIMEOUT:-360} bash scripts/wait_done.sh

# --- город дронов: КАРТОГРАФИРОВАНИЕ (полный облёт поля, docker) ---
# То же, что local-city, но в docker. Собрать всю карту = осмотреть 25/25 клеток.
demo-city:
	-docker compose down -v >/dev/null 2>&1
	@set -a; [ -f .env ] && . ./.env; set +a; \
	files="-f docker-compose.yml"; \
	case "$${MODEL_PROVIDER:-mock}" in sverk|anthropic|openai|ollama) \
	  files="$$files -f docker-compose.egress.yml";; esac; \
	TASK=survey SCENARIO=survey-city WAIT_SCALE=$${WAIT_SCALE:-0.05} \
	  docker compose $$files up --build -d; \
	echo "city map dashboard: http://localhost:8080/survey  (brain: $${MODEL_PROVIDER:-mock})"; \
	DC="docker compose $$files" TIMEOUT=$${TIMEOUT:-360} bash scripts/wait_done.sh

# --- distributed mode (drones talk to a central hub over HTTP) ---
# Single-host demo of the on-drone wiring: hub + coordinator + drones(HttpBoard).
demo-distributed:
	-docker compose -f docker-compose.distributed.yml down -v >/dev/null 2>&1
	docker compose -f docker-compose.distributed.yml up --build -d
	@echo "hub + dashboard: http://localhost:8080"
	@DC="docker compose -f docker-compose.distributed.yml" WAIT_SVC=hub bash scripts/wait_done.sh

down-distributed:
	docker compose -f docker-compose.distributed.yml down

# Multi-host: run on the orchestrator box. Add RESET=1 to start a fresh board.
hub:
	$(if $(filter 1 true yes,$(RESET)),-docker compose -f docker-compose.hub.yml down -v >/dev/null 2>&1,)
	HUB_TOKEN=$${HUB_TOKEN:-} docker compose -f docker-compose.hub.yml up --build -d
	@echo "orchestrator hub + dashboard: http://localhost:8080"

# Multi-host: run on each robot. Usage:
#   make drone AGENT_ID=drone-5 ROLE=scout HUB_URL=http://<orchestrator>:8080 \
#        HANDLER_ID=team-7 FLEET=city [HUB_TOKEN=..] [TASK=survey]
#   painters:  make drone AGENT_ID=painter-5 ROLE=painter TASK=painting FLEET=painter HUB_URL=...
# AGENT_ID можно опустить, если борт уже привязан (LED-регистрация на /fleet —
# привязка живёт в постоянной памяти, volume openclaw-binding). См. docs/fleet.md.
drone:
	@test -n "$(ROLE)" && test -n "$(HUB_URL)" || \
	  { echo "usage: make drone ROLE=scout HUB_URL=http://<orchestrator>:8080 [AGENT_ID=drone-5] [HANDLER_ID=team-7] [FLEET=city|painter] [HUB_TOKEN=..] [TASK=survey|painting]"; exit 1; }
	AGENT_ID=$${AGENT_ID:-} ROLE=$(ROLE) HUB_URL=$(HUB_URL) HUB_TOKEN=$${HUB_TOKEN:-} \
	  HANDLER_ID=$${HANDLER_ID:-} FLEET=$${FLEET:-} BRIDGE_IMAGE=$${BRIDGE_IMAGE:-} \
	  TASK=$${TASK:-} SCENARIO=$${SCENARIO:-} \
	  docker compose -p $${AGENT_ID:-drone} -f docker-compose.drone.yml up --build -d
	@echo "$${AGENT_ID:-<из привязки>} ($(ROLE)) -> $(HUB_URL) [$${HANDLER_ID:-no-handler}/$${FLEET:-any}]"

down:
	docker compose down

logs:
	docker compose logs -f

# --- пауза всех сценариев (замена аккумуляторов на дронах) ---
# Дроны садятся (bridge /land), фазовая машина замирает, дедлайны сдвигаются;
# resume — взлёт + ресинк реальной позиции из бриджа. Работает для local-* и
# для docker-стеков (viz слушает :8080 и там, и там; VIZ_PORT переопределяет).
pause:
	@curl -sf -X POST "http://localhost:$${VIZ_PORT:-8080}/pause" \
	  -H 'content-type: application/json' -H 'x-pause: 1' \
	  $${HUB_TOKEN:+-H "authorization: Bearer $$HUB_TOKEN"} \
	  -d '{"paused": true, "reason": "замена аккумуляторов"}' \
	  && echo " — пауза: дроны садятся" \
	  || echo "не вышло: viz на :$${VIZ_PORT:-8080} недоступен, или volume read-only (в docker: make pause-docker)"
resume:
	@curl -sf -X POST "http://localhost:$${VIZ_PORT:-8080}/pause" \
	  -H 'content-type: application/json' -H 'x-pause: 1' \
	  $${HUB_TOKEN:+-H "authorization: Bearer $$HUB_TOKEN"} \
	  -d '{"paused": false}' \
	  && echo " — пауза снята: дроны взлетают, позиции ресинкаются" \
	  || echo "не вышло: viz на :$${VIZ_PORT:-8080} недоступен (в docker: make resume-docker)"
# В базовом docker-компоузе viz монтирует доску read-only (§1) — пишем паузу
# через контейнер координатора (у него volume rw).
pause-docker:
	docker compose exec -T coordinator python -c "import sys;sys.path.insert(0,'/app/agent');from bb import Blackboard,now_iso;b=Blackboard();b.write_pause({'paused':True,'reason':'замена аккумуляторов','by':'operator','ts':now_iso()});b.append_event({'kind':'pause','paused':True,'reason':'замена аккумуляторов','ts':now_iso()});print('paused')"
resume-docker:
	docker compose exec -T coordinator python -c "import sys;sys.path.insert(0,'/app/agent');from bb import Blackboard,now_iso;b=Blackboard();b.write_pause({'paused':False,'by':'operator','ts':now_iso()});b.append_event({'kind':'pause','paused':False,'ts':now_iso()});print('resumed')"

# Print the current phase + verdict from the running stack.
verdict:
	@docker compose exec -T viz python -c "import json;p=json.load(open('/blackboard/state/phase.json'));d=json.load(open('/blackboard/state/decision.json'));print('phase=',p['phase'],'verdict=',d.get('result'))"

build:
	docker compose build

# Wipe the blackboard volume (alias for reset, kept for back-compat).
clean: reset

# --- run without Docker (fast iteration; mock brain) ---
local:
	bash scripts/run_local.sh
local-painters:
	TASK=painting SCENARIO=painters-1 bash scripts/run_local.sh
# Turn-based debate/decision engine (moderator + debaters). Swap the topic in
# test_fixtures/debate-1/map.json, or point SCENARIO at your own. Set a real
# MODEL_PROVIDER for actual arguments (mock brain only exercises the protocol).
# Test stand (live speaker + all arguments): http://localhost:8080/debate
local-debate:
	TASK=debate SCENARIO=debate-1 bash scripts/run_local.sh
# Поиск груза на поле 5×5 (см. demo-survey). Живой стенд: :8080/survey
local-survey:
	TASK=survey SCENARIO=survey-1 bash scripts/run_local.sh
# Город дронов — КАРТОГРАФИРОВАНИЕ: 4 дрона делят поле 5×5 в чате и облетают
# КАЖДУЮ клетку (JSON-планы LLM), чтобы собрать всю карту целиком. Груза нет,
# VLM не нужен. Пунктирные кольца на дашборде — куда собрался каждый дрон.
# Живой стенд: http://localhost:8080/survey
local-city:
	TASK=survey SCENARIO=survey-city bash scripts/run_local.sh
# То же, но ровер — РЕАЛЬНЫЙ куб в Gazebo (sverk_sitl / PX4 SITL + Gazebo
# Harmonic), 4 дрона зеркалятся моделями в Gazebo. Дроны собирают карту →
# ровер выезжает из точки А к ПОЖАРУ (точка Б) и катится туда в симе.
# Требует поднятый контейнер sverk_sitl. Стенд: http://localhost:8080/survey
local-city-gazebo:
	GAZEBO_SIM=1 TASK=survey SCENARIO=survey-city bash scripts/run_local.sh
# test-3x3: ОДИН борт сканирует поле 3×3, ДВА пилота-агента спорят (живой LLM)
# за маршрут; оператор в паузе переключает, чей маршрут летит дрон. Без ровера,
# без пожара/доставки — чистый E2E смоук стека. Фронт: http://localhost:8095/test
# Живой спор: MODEL_PROVIDER=sverk make local-test3x3
local-test3x3:
	bash scripts/test_3x3.sh
# --- frontend (React + TS studio dashboard) ---
# `make web` force-rebuilds; the `frontend/dist` file-target builds it only when
# missing, so it can be an order-only prereq of the local run targets.
web:
	cd frontend && npm install --no-audit --no-fund && npm run build
frontend/dist:
	cd frontend && npm install --no-audit --no-fund && npm run build

# Collab painting: 4 drones agree a subject, then EACH renders its OWN colour as
# z-layered shapes into ONE shared canvas (not 4 quadrants). KEEP_ALIVE so the
# dashboard "New run" button can restart it. Dashboard: :8080/studio
local-collab: frontend/dist
	KEEP_ALIVE=1 PAINT_MODE=collab TASK=painting SCENARIO=painters-1 bash scripts/run_local.sh
# FULL decentralized studio on the REAL brain (uses MODEL_PROVIDER from .env, e.g.
# sverk): thin facilitator + free stigmergic drone chat + private threads → vote →
# each drone paints its OWN colour with MAX expressive freedom (whole canvas,
# COLLAB_SHAPES each). Agents stay alive so the "↻ New run" button reruns from
# scratch. Watch it live at http://localhost:8080/studio
local-studio: frontend/dist
	STUDIO_CHAT=1 PAINT_MODE=collab COLLAB_LLM_SHAPES=1 COLLAB_FREE=1 COLLAB_SHAPES=5 \
	  KEEP_ALIVE=1 TASK=painting SCENARIO=painters-1 bash scripts/run_local.sh
# --- headless: прогон сценария БЕЗ фронта + текстовый разбор ------------------
# Фронт (frontend-recovered/dist) устарел и не рисует поле города дронов; бэкенд
# работает. Этот режим гоняет протокол без браузера и печатает, что дроны
# увидели, вердикт, артефакты и примеры реплик (для проверки русского языка).
#   make headless                          — город дронов (safe_passage), mock
#   MODEL_PROVIDER=sverk make headless      — реальный мозг (видно русский текст)
#   TASK=survey make headless               — другой сценарий
headless:
	@TASK=$${TASK:-safe_passage} SCENARIO=$${SCENARIO:-} \
	  MODEL_PROVIDER=$${MODEL_PROVIDER:-} TIMEOUT=$${TIMEOUT:-60} \
	  bash scripts/headless.sh

stop-local:
	bash scripts/stop_local.sh
