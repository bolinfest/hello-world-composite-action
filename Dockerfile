FROM ubuntu:22.04

# Consider?
# FROM python:3.12-slim

# https://serverfault.com/a/1016972 to ensure installing tzdata does not
# result in a prompt that hangs forever.
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Update and install some basic packages to register a PPA.
RUN apt-get -y update

RUN apt-get -y install python3

COPY process_config.py /process_config.py

ENTRYPOINT ["/process_config.py"]
