# This script dumps waveforms to wav-copy format wav ark, including sample rate and int16 sequence.
"""
Author: Zhihao Du
Date: 2023.03.29
Description: Convert wav, flac and ark files to mono waveform files with given sampling rate.
"""
import logging
import warnings
warnings.filterwarnings("ignore")
import os
import time
import argparse
import numpy as np
from funcodec.utils.misc import get_logger
import kaldiio
import librosa
import soundfile


def main(args):
    logger = get_logger(log_level=logging.INFO)
    rank = int(os.environ['LOCAL_RANK'])
    threads_num = int(os.environ['WORLD_SIZE'])
    sr, sample_bits = args.sample_rate, 16
    out_dir = args.out_dir
    logger.info("rank {}/{}: Sample rate {}, sample bits {}, out_dir {}.".format(
        rank, threads_num, sr, sample_bits, out_dir
    ))
    if out_dir is not None:
        if rank == 0:
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
        else:
            while not os.path.exists(out_dir):
                time.sleep(0.5)

    all_recs = []
    if args.wav_scp is not None and len(args.wav_scp) > 0:
        for one_line in open(args.wav_scp, "rt", encoding="utf-8"):
            path = one_line.strip()
            key, path = path.split(" ", maxsplit=1)
            all_recs.append((key, path))
    else:
        for one_line in open(args.wav_list, "rt", encoding="utf-8"):
            path = one_line.strip()
            key = os.path.basename(path).rsplit(".", 1)[0]
            all_recs.append((key, path))
    all_recs.sort(key=lambda x: x[0])
    local_all_recs = all_recs[rank::threads_num]

    out_path = os.path.join(out_dir, f"part{rank:02d}")
    wav_writer = kaldiio.WriteHelper(f"ark,scp,f:{out_path}.ark,{out_path}.scp")
    meeting_count = 0
    for i, (uttid, wav_path) in enumerate(local_all_recs):
        # skip files not ending with wav
        if not wav_path.lower().endswith(".wav") and \
                not wav_path.lower().endswith(".flac") and \
                not (".ark" in wav_path.lower() and ":" in wav_path):
            logger.warning("rank {}/{}: Skip {} since {} file format is not wav or flac or ark.".format(
                rank, threads_num, uttid, wav_path
            ))
            continue
        if not (".ark" in wav_path.lower() and ":" in wav_path):
            # Use librosa to deal with multi-channels and different sampling rate
            wav, sr = librosa.load(wav_path, dtype=np.float32, sr=sr, mono=True)
        else:
            wav = kaldiio.load_mat(wav_path)
            if isinstance(wav, tuple):
                if isinstance(wav[0], int):
                    sr, wav = wav
                else:
                    wav, sr = wav
            if (np.max(np.abs(wav)) > 1.0) or args.force_rescale:
                wav = wav / np.max(np.abs(wav)) * 0.9

        wav_writer(uttid, (sr, (wav * (2**15)).astype(np.int16)))

        if i % 100 == 0:
            logger.info("{}/{}: process {}.".format(rank, threads_num, uttid))

        meeting_count += 1

    wav_writer.close()
    logger.info("{}/{}: Complete {} records.".format(rank, threads_num, meeting_count))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--wav_list',
                        type=str,
                        default=None,
                        help="wav path list")
    parser.add_argument('--wav_scp',
                        type=str,
                        default=None,
                        help="kaldi-style wav path script")
    parser.add_argument('--local_rank',
                        type=int,
                        default=0,
                        help="local rank of gpu")
    parser.add_argument('--out_dir',
                        type=str,
                        default=None,
                        help="The output dir to save rttms and wavs")
    parser.add_argument('--sample_rate',
                        type=int,
                        default=16_000,
                        help="The expected sample rate.")
    parser.add_argument("--output_suffix",
                        type=str,
                        default="",
                        help="The suffix added to the end of file name.")
    parser.add_argument("--force_rescale",
                        type=bool,
                        default=False,
                        help="force rescale")
    args = parser.parse_args()
    main(args)
