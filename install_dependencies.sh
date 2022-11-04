#!/bin/bash
sudo apt update

# ETC
sudo apt-get install -y wget curl vim apt-utils tzdata liblzma-dev software-properties-common build-essential
sudo apt-get install -y autoconf automake libtool make g++ unzip cmake
sudo apt-get install -y libprotobuf* protobuf-compiler ninja-build
sudo apt-get install -y libsm6 libxext6 libxrender-dev
sudo apt-get install -y libgl1-mesa-glx pkg-config libjpeg-dev libjpeg-turbo8-dev libtiff5-dev libpng-dev libv4l-dev v4l-utils libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
sudo apt-get install -y libatlas-base-dev gfortran libeigen3-dev ffmpeg libavcodec-dev libavformat-dev libswscale-dev libxvidcore-dev libx264-dev libxine2-dev
sudo apt-get install -y mesa-utils libgl1-mesa-dri libgtk2.0-dev libgtkgl2.0-dev libgtkglext1-dev libgtk-3-dev
sudo apt-get install -y libturbojpeg libyajl2 libyajl-dev
sudo apt-get install -y lmdb-utils

# chrome dependecies
sudo apt-get install -y gconf-service libasound2 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgcc1 libgconf-2-4 libgdk-pixbuf2.0-0 libglib2.0-0 libgtk-3-0
sudo apt-get install -y libnspr4 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2
sudo apt-get install -y libxrender1 libxss1 libxtst6 ca-certificates fonts-liberation libappindicator1 libnss3 lsb-release xdg-utils

# Install google-chrome (version 103.0.5060.xxx) on ubuntu.
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
sudo apt-get update
sudo apt-get install google-chrome-stable=103.0.5060.134-1

# Download executable google-chrome.
wget https://chromedriver.storage.googleapis.com/103.0.5060.24/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
mv chromedriver resources/chromedriver_linux64_103.0.5060.24
rm chromedriver_linux64.zip

# Languages
sudo apt-get -y install locales language-selector-common
sudo apt-get -y install $(check-language-support)
sudo apt-get -y install `check-language-support -l en`
sudo apt-get -y install `check-language-support -l ko`
sudo apt-get -y install `check-language-support -l ja`
sudo apt-get -y install `check-language-support -l zh`
sudo apt-get -y install `check-language-support -l es`
sudo apt-get -y install `check-language-support -l fr`
sudo apt-get -y install `check-language-support -l it`
sudo apt-get -y install `check-language-support -l de`
sudo apt-get -y install `check-language-support -l pt`

sudo apt-get --fix-broken install
