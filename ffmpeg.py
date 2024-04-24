import platform
import os
from os.path import abspath, dirname

import configparser
import logging
import os
import sys
import ffmpeg
import wave

isDev = setupData["isDev"]
logger = setupData["logger"]

import sys
root_path = f'.' if isDev else f'./resources/app' # The root directories are different in dev/prod
if not isDev:
	sys.path.append("./resources/app")

def setup(data=None):
	global logger
	logger.log(f'Setting up plugin. App version: {data["appVersion"]} | CPU only: {data["isCPUonly"]} | Development mode: {data["isDev"]}')

def apply_batch(data=None):
	global apply
	# logger.log(data)
	data['outfile'] = data['linesBatch'][0][5]
	apply(data)

def apply(data=None):
	global root_path, isDev, platform, os, csv, ffmpeg, wave, logger
	options = {}
	try:
		options = data['pluginsContext']['ffmpeg']
	except:
		return

	if len(options) == 0:
		try:
			options = data['ffmpeg']
		except:
			return

	if len(options) == 0:
		return

	# ~xVASynth's python/audio_post.py run_audio_post function
	ffmpeg_path = 'ffmpeg' if platform.system() == 'Linux' else f'{"./resources/app" if not isDev else "."}/python/ffmpeg.exe'
	input_path = data['outfile']
	output_path = data['outfile'].replace(".wav", "_temp.wav")

	stream = ffmpeg.input(input_path)

	ffmpeg_options = {"ar": options["hz"]}

	ffmpeg_options["af"] = []
	if (
		"padStart" in options.keys()
		and options["padStart"]
	):
		ffmpeg_options["af"].append(f'adelay={options["padStart"]}')
		logger.debug('padStart')
	if (
		"padEnd" in options.keys()
		and options["padEnd"]
	):
		ffmpeg_options["af"].append(f'apad=pad_dur={options["padEnd"]}ms')
		logger.debug('padEnd')


	# Pitch
	hz = 22050
	if (
		"useSR" in data.keys() and data["useSR"]
		or "useCleanup" in data.keys() and data["useCleanup"]
	):
		hz = 48000
		logger.debug('48kHz')

	if (
		"pitchMult" in options.keys()
		and options["pitchMult"]
	):
		ffmpeg_options["af"].append(f'asetrate={hz*(options["pitchMult"])},atempo=1/{options["pitchMult"]}')
		logger.debug('pitchMult')
	# Tempo
	if (
		"tempo" in options.keys()
		and options["tempo"]
	):
		ffmpeg_options["af"].append(f'atempo={options["tempo"]}')
		logger.debug('tempo')

	if (
		"amplitude" in options.keys()
		and options["amplitude"]
	):
		ffmpeg_options["af"].append(f'volume={options["amplitude"]}')
		logger.debug('amplitude')

	ffmpeg_options["af"].append("adeclip,adeclick")

	if "useNR" in options.keys() and options["useNR"]:
		ffmpeg_options["af"].append(f'afftdn=nr={options["nr"]}:nf={options["nf"]}:tn=0')
		logger.debug('useNR')

	ffmpeg_options["af"] = ",".join(ffmpeg_options["af"])



	if (
		"bit_depth" in options.keys()
		and options["bit_depth"]
	):
		ffmpeg_options["acodec"] = options["bit_depth"]
		logger.debug('bit_depth')

	if "mp3" in output_path:
		ffmpeg_options["c:a"] = "libmp3lame"
		logger.debug('mp3')


	if os.path.exists(output_path):
		try:
			os.remove(output_path)
		except:
			pass

	stream = ffmpeg.output(stream, output_path, **ffmpeg_options)
	out, err = (ffmpeg.run(stream, cmd=ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True))

	# The "filter_complex" option can't be used in the same stream as the normal "filter", so have to do two ffmpeg runs
	# reverb

	# denoising
	if "deessing" in options and options["deessing"]>0:
		stream = ffmpeg.input(output_path)
		ffmpeg_options = {}
		ffmpeg_options["filter_complex"] = f'deesser=i={options["deessing"]}:m=0.5:f=0.5:s=o'
		stream = ffmpeg.output(stream, input_path, **ffmpeg_options)
		out, err = (ffmpeg.run(stream, cmd=ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True))
		os.remove(output_path)
		logger.debug('deesing applied')

		# skip rest
		return

	if "reverb" in options and options["reverb"]:
		stream = ffmpeg.input(output_path)
		ffmpeg_options = {}
		ffmpeg_options["i"] = f'{root_path}/plugins/ffmpeg/church_clap_22.wav'

		ffmpeg_options["filter_complex"] = f'[0] [1] afir=dry=10:wet=10 [reverb]; [0] [reverb] amix=inputs=2:weights=1 5'
		stream = ffmpeg\
			.output(stream, input_path.replace(".wav", "_temp_reverb.wav"), **ffmpeg_options)
		out, err = (ffmpeg.run(stream, cmd=ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True))
		logger.info('reverb applied')

		# increase volume and do volume fade-out at end
		# get duration for fade-out
		with wave.open(input_path.replace(".wav", "_temp_reverb.wav"), 'r') as wf:
		    frames = wf.getnframes()
		    rate = wf.getframerate()
		startFade = frames / float(rate) - options["padEnd"] / 1000

		stream = ffmpeg.input(input_path.replace(".wav", "_temp_reverb.wav"))
		ffmpeg_options = {}
		# increase volume
		boostDb = options["boostdB"]
		ffmpeg_options["af"] = f"volume={boostDb}dB"
		# declare fade-out
		ffmpeg_options["af"] += f",afade=t=out:st={startFade}:d=1"
		stream = ffmpeg\
			.output(stream, input_path, **ffmpeg_options)
		out, err = (ffmpeg.run(stream, cmd=ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True))
		os.remove(input_path.replace(".wav", "_temp_reverb.wav"))
		logger.debug('volume increased; fade-out applied')

		# skip rest
		return

	os.remove(input_path)
	os.rename(output_path, input_path)
