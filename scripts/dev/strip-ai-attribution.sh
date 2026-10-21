#!/usr/bin/env bash
grep -viE '^Co-[Aa]uthored-[Bb]y:' | grep -viE '^Made-with:'
