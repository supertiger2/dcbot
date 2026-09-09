FROM debian:13

WORKDIR /
RUN set -eu && \
	mkdir /code && \
	apt-get update && \
	apt-get upgrade --no-install-recommends -y && \
	apt-get install --no-install-recommends -y build-essential && \
	apt-get install --no-install-recommends -y ca-certificates python3-full python3-pip python3-venv python3-dev libffi-dev libnacl-dev libraqm-dev libimagequant-dev libwebp-dev liblcms2-dev libfreetype6-dev libtiff-dev zlib1g-dev libjpeg-dev libpng-dev && \
	python3 -m venv /venv/ && \
	export PATH="/venv/bin:$PATH" && \
	pip3 install --no-cache-dir requests pymongo motor Pillow "py-cord[speed]" python-dotenv && \
	apt-get remove -y build-essential && \
	apt-get autoremove -y

ENV PATH="/venv/bin:$PATH"

CMD ["python3", "/code/dcbot.py"]
