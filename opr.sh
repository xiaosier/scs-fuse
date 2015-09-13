#!/bin/bash
ps -ef|grep online|grep -v grep|awk {'print $2'}|xargs kill
python online.py /data2/ -o allow_other