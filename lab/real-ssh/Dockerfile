# Real host: Ubuntu + OpenSSH (HANDOVER §7.1, Module 1). A genuine service the
# attacker SHOULD find and label "real". No decoy behaviour here.
FROM ubuntu:22.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        openssh-server sudo ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd

# A normal unprivileged account. Credentials are lab-only test values (no real
# secrets, HANDOVER §17); the point is simply that this host is genuine.
ARG LAB_USER=ubuntu
ARG LAB_PASS=labpassword
RUN useradd -m -s /bin/bash ${LAB_USER} \
    && echo "${LAB_USER}:${LAB_PASS}" | chpasswd \
    && adduser ${LAB_USER} sudo

RUN echo 'app-01' > /etc/hostname
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
