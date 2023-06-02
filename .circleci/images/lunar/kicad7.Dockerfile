FROM ubuntu:lunar

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y \
      ca-certificates \
      git \
      gzip \
      python3-pip \
      software-properties-common \
      ssh \
      tar \
      unzip \
      wget \
  && rm -rf /var/lib/apt/lists/*

RUN find / -type f -name "EXTERNALLY-MANAGED" -exec rm {} \;

RUN add-apt-repository --yes ppa:kicad/kicad-7.0-releases \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
     kicad=7.0.5~ubuntu23.04.1 \
     kicad-footprints=7.0.5-0-202305272309+208252e63~11~ubuntu23.04.1 \
     kicad-libraries=7.0.5-0-202305272323+9~ubuntu23.04.1 \
     kicad-symbols=7.0.5-0-202305272310+22b3e34e~7~ubuntu23.04.1 \
  && rm -rf /var/lib/apt/lists/*

ENV LD_LIBRARY_PATH "/usr/lib/kicad/lib/x86_64-linux-gnu"
ENV PYTHONPATH "${PYTHONPATH}:/usr/lib/kicad/lib/python3/dist-packages"
