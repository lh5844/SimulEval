from argparse import ArgumentParser

from fairseq.data.encoders import build_bpe

from simuleval.utils import entrypoint
from simuleval.agents import TextToTextAgent
from simuleval.agents.actions import ReadAction, WriteAction
from simuleval.agents.pipeline import AgentPipeline
from simuleval.agents.states import AgentStates

@entrypoint
class DummySegmentAgent(TextToTextAgent):
    """
    This agent just splits on space
    """

    def __init__(self, args):
        super().__init__(args)
        self.segment_k = args.segment_k

    @classmethod
    def from_args(cls, args, **kwargs):
        return cls(args)

    def add_args(parser: ArgumentParser):
        parser.add_argument(
            "--segment-k",
            type=int,
            help="Output segments with this many words",
            required=True,
        )

    def policy(self, states: AgentStates):
        if len(states.source) == self.segment_k or states.source_finished:
            out = " ".join(states.source)
            states.source = []
            return WriteAction(out, finished=states.source_finished)
        return ReadAction()


class SentencePieceModelDetokenizerAgent(TextToTextAgent):
    def __init__(self, args):
        super().__init__(args)
        self.args.bpe = "sentencepiece"
        spm_processor = build_bpe(self.args)
        self.spm_processor = spm_processor
        self.detokenize_only = args.detokenize_only

    @classmethod
    def from_args(cls, args, **kwargs):
        return cls(args)

    def add_args(parser: ArgumentParser):
        parser.add_argument(
            "--sentencepiece-model",
            type=str,
            help="Path to sentencepiece model.",
            required=True,
        )
        parser.add_argument(
            "--detokenize-only",
            action="store_true",
            default=False,
            help=(
                "Run detokenization without waiting for new token. By default(False),"
                "wait for beginning of next word before finalizing the previous word"
            ),
        )

    def policy(self, states: AgentStates):
        possible_full_words = self.spm_processor.decode(
            " ".join([x for x in states.source])
        )
        # issue is when the starting word is in the previous segment 
        if self.detokenize_only and len(states.source) > 0:
            start_word = "▁"
            source_text = states.source[0]
            states.source = []
            if len(possible_full_words) == 0 and not states.source_finished:
                return ReadAction()
            else:
                word_boundary = False
                if start_word not in source_text[0]: 
                    word_boundary = True
                return WriteAction(possible_full_words, states.source_finished, word_boundary)

        if states.source_finished:
            return WriteAction(possible_full_words, True)
        elif len(possible_full_words.split()) > 1:
            full_words, last_word = (
                possible_full_words.split()[:-1],
                possible_full_words.split()[-1],
            )
            states.source = [self.spm_processor.encode(last_word)]
            return WriteAction(" ".join(full_words), finished=False)
        else:
            return ReadAction()


class DummyPipeline(AgentPipeline):
    pipeline = [DummySegmentAgent, SentencePieceModelDetokenizerAgent]
