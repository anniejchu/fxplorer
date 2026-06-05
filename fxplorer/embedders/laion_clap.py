from pathlib import Path
from typing import Union, List, Optional

import torch
import laion_clap
from audiotools import AudioSignal

from fxplorer.helper import AbstractCLAPWrapper, download_file
from fxplorer.constants import PRETRAINED_DIR, DEVICE


class LAIONCLAPWrapper(AbstractCLAPWrapper):
    def __init__(
        self,
        clap_model: Optional[Union[str, int]] = None,
        audio_model: Optional[Union[str, int]] = None,
        ckpt_path: Optional[Union[str, Path]] = None,
        enable_fusion: bool = False,
        device: Optional[str] = None,
    ):
        """
        Initialize a LAION CLAP wrapper.

        Args:
            clap_model: str or int. Name or index of the CLAP model checkpoint. If None, defaults to music model.
            audio_model: str or int. Name or index of the CLAP audio model. If None, defaults to HT
            T-base.
            ckpt_path: str or Path. Optional path to an existing checkpoint file to load from directly.
            enable_fusion: bool. Whether to enable fusion (default: False).
        """
        CLAP_MODELS = [
            '630k-best.pt',
            '630k-audioset-best.pt',
            '630k-fusion-best.pt',
            '630k-audioset-fusion-best.pt',
            'music_audioset_epoch_15_esc_90.14.pt',
            'music_speech_epoch_15_esc_89.25.pt',
            'music_speech_audioset_epoch_15_esc_89.98.pt',
        ]

        CLAP_AUDIO_MODELS = [
            'HTSAT-base',
            'HTSAT-large',
            'HTSAT-tiny',
            'HTSAT-tiny-win-1536',
            'PANN-6',
            'PANN-10',
            'PANN-14',
            'PANN-14-fmax-8k-20s',
            'PANN-14-fmax-18k',
            'PANN-14-tiny-transformer',
            'PANN-14-win-1536',
        ]

        self.CLAP_SAMPLE_RATE = 48_000
        self.device = device or DEVICE
        CLAP_PRETRAINED_DIR = PRETRAINED_DIR / "clap"
        CLAP_DOWNLOAD_LINK = 'https://huggingface.co/lukewys/laion_clap/resolve/main/'

        # Resolve CLAP model selection
        if isinstance(clap_model, int):
            ckpt = CLAP_MODELS[clap_model]
        elif isinstance(clap_model, str):
            ckpt = clap_model
        else:
            ckpt = CLAP_MODELS[4]  # Default: music model

        # Resolve audio model selection
        if isinstance(audio_model, int):
            audio_model_name = CLAP_AUDIO_MODELS[audio_model]
        elif isinstance(audio_model, str):
            audio_model_name = audio_model
        else:
            audio_model_name = 'HTSAT-base'  # Default audio model

        # Determine checkpoint path
        if ckpt_path:
            ckpt_pth = Path(ckpt_path)
        else:
            ckpt_pth = CLAP_PRETRAINED_DIR / ckpt
            if not ckpt_pth.exists():
                CLAP_PRETRAINED_DIR.mkdir(exist_ok=True, parents=True)
                print(f"Downloading weights for checkpoint {ckpt}")
                ckpt_pth = download_file(CLAP_DOWNLOAD_LINK + ckpt, CLAP_PRETRAINED_DIR)

        # Initialize CLAP module
        self.model = laion_clap.CLAP_Module(
            enable_fusion=enable_fusion,
            amodel=audio_model_name,
        )

        # Handle potential DataParallel state dicts
        import numpy.core.multiarray
        torch.serialization.add_safe_globals([numpy.core.multiarray.scalar])

        ckpt_data = torch.load(ckpt_pth, map_location=self.device, weights_only=False)
        print(f"Loaded checkpoint from {ckpt_pth}")

        state_dict = ckpt_data.get('state_dict', ckpt_data)
        new_state_dict = {k.replace('module.', ''): v for k, v in state_dict.items()}

        missing_keys, unexpected_keys = self.model.model.load_state_dict(new_state_dict, strict=False)
        if missing_keys:
            print(f"Warning: {len(missing_keys)} missing keys")
        if unexpected_keys and unexpected_keys != ['text_branch.embeddings.position_ids']:
            print(f"Warning: Unexpected keys: {unexpected_keys}")

        self.model = self.model.to(self.device)
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad = False

    def preprocess_audio(self, signal: AudioSignal, quantize: bool = False) -> AudioSignal:
        signal = signal.resample(self.CLAP_SAMPLE_RATE)
        x = signal.samples.mean(1, keepdim=False)

        if quantize:
            quant = (x.clone().clamp(-1, 1) * 32767.).to(torch.int16)
            quant = (quant / 32767.).to(torch.float32)
            x = x + (quant - x).detach()

        signal.samples = x.unsqueeze(1)
        return signal

    def get_audio_embeddings(self, signal: AudioSignal) -> torch.Tensor:
        x = self.preprocess_audio(signal).samples.squeeze(1)
        return self.model.get_audio_embedding_from_data(x=x, use_tensor=True)

    def get_text_embeddings(self, text: Union[str, List[str]]) -> torch.Tensor:
        if isinstance(text, str):
            text = [text]
        text_padded = text + ["<null>"]
        return self.model.get_text_embedding(text_padded, use_tensor=True)[:-1]

    def compute_similarity(self, audio_emb: torch.Tensor, text_emb: torch.Tensor) -> torch.Tensor:
        audio_emb = audio_emb / audio_emb.norm(dim=-1, keepdim=True)
        text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
        return audio_emb @ text_emb.T

    @property
    def sample_rate(self):
        return self.CLAP_SAMPLE_RATE
