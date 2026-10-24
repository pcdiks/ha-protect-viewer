FROM ghcr.io/home-assistant/amd64-base:3.22

ARG GO2RTC_VERSION=1.9.14
ARG GO2RTC_SHA256=32d616af226bd731678ffde328b94cfb94e30339bfefc469cfb76323144615a6

RUN apk add --no-cache python3 py3-aiohttp \
    && curl -fsSL -o /usr/local/bin/go2rtc \
        "https://github.com/AlexxIT/go2rtc/releases/download/v${GO2RTC_VERSION}/go2rtc_linux_amd64" \
    && echo "${GO2RTC_SHA256}  /usr/local/bin/go2rtc" | sha256sum -c - \
    && chmod +x /usr/local/bin/go2rtc

COPY app /opt/app
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
