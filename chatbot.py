import os


#Cloning Github Page

os.system("git clone --branch v0.1 --recursive https://github.com/daniel-kukiela/nmt-chatbot.git")

#preparing Data
os.system("cd nmt-chatbot && pip install -r requirements.txt && cd setup && python prepare_data.py")

#Copying The Files
os.system("cp  misc_utils.py nmt-chatbot/nmt/nmt/utils/misc_utils.py")

#Training
os.system("python nmt-chatbot/train.py")

#copying FIles 

import os
tmp='nmt-chatbot/'
a=list(os.listdir(tmp))
print(a)
for f in a:
  b="cp -r %s ."%(tmp+f)
  os.system(b)

os.system('rm -r nmt-chatbot')






import sys
import os
sys.path.append(os.path.realpath(os.path.dirname(__file__)))
sys.path.append(os.path.realpath(os.path.dirname(__file__)) + "/nmt")
import argparse
from setup.settings import hparams, out_dir
from nmt import nmt
import tensorflow as tf
from core.tokenizer import tokenize, detokenize
from core.sentence import score_answers, replace_in_answers
import colorama


current_stdout = None

# That will not be as easy as training script, as code relies on input and output file in deep levels of code
# It also outputs massive amount of info
# We have to make own script for inference, so we could:cd ..
# - use it in interactive mode
# - import for use in other code
# - use input and output of our choice (so, for example, file as input and console as output,
#   or even console as input and file as output (but why? ;) ), etc)
# Why that nmt module doesn't give us some easy to use interface?

# Start inference "engine"
def do_start_inference(out_dir, hparams):

    # Silence all outputs
    #os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    global current_stdout
    current_stdout = sys.stdout
    sys.stdout = open(os.devnull, "w")

    # Modified autorun from nmt.py (bottom of the file)
    # We want to use original argument parser (for validation, etc)
    nmt_parser = argparse.ArgumentParser()
    nmt.add_arguments(nmt_parser)
    # But we have to hack settings from our config in there instead of commandline options
    flags, unparsed = nmt_parser.parse_known_args(['--'+k+'='+str(v) for k,v in hparams.items()])
    # And now we can run TF with modified arguments
    #tf.app.run(main=nmt.main, argv=[os.getcwd() + '\nmt\nmt\nmt.py'] + unparsed)

    # Add output (model) folder to flags
    flags.out_dir = out_dir

    # Make hparams
    hparams = nmt.create_hparams(flags)

    ## Train / Decode
    if not tf.gfile.Exists(flags.out_dir):
        nmt.utils.print_out("# Model folder (out_dir) doesn't exist")
        sys.exit()

    # Load hparams from model folder
    hparams = nmt.create_or_load_hparams(flags.out_dir, hparams, flags.hparams_path, save_hparams=True)

    # Choose checkpoint (provided with hparams or last one)
    if not flags.ckpt:
        flags.ckpt = tf.train.latest_checkpoint(flags.out_dir)

    # Create model
    if not hparams.attention:
        model_creator = nmt.inference.nmt_model.Model
    elif hparams.attention_architecture == "standard":
        model_creator = nmt.inference.attention_model.AttentionModel
    elif hparams.attention_architecture in ["gnmt", "gnmt_v2"]:
        model_creator = nmt.inference.gnmt_model.GNMTModel
    else:
        raise ValueError("Unknown model architecture")
    infer_model = nmt.inference.model_helper.create_infer_model(model_creator, hparams, None)

    return (infer_model, flags, hparams)

# Inference
def do_inference(infer_data, infer_model, flags, hparams):

    # Disable TF logs for a while
    # Workaround for bug: https://github.com/tensorflow/tensorflow/issues/12414
    # Already fixed, available in nightly builds, but not in stable version
    # Maybe that will stay here to silence any outputs
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    global current_stdout
    if not current_stdout:
        current_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")

    # Spawn new session
    with tf.Session(graph=infer_model.graph, config=nmt.utils.get_config_proto()) as sess:

        # Load model
        loaded_infer_model = nmt.inference.model_helper.load_model(infer_model.model, flags.ckpt, sess, "infer")

        # Run model (translate)
        sess.run(
            infer_model.iterator.initializer,
            feed_dict={
                infer_model.src_placeholder: infer_data,
                infer_model.batch_size_placeholder: hparams.infer_batch_size
            })


        # calculate number of translations to be returned
        num_translations_per_input = max(min(hparams.num_translations_per_input, hparams.beam_width), 1)

        answers = []
        while True:
            try:

                nmt_outputs, _ = loaded_infer_model.decode(sess)

                if hparams.beam_width == 0:
                    nmt_outputs = nmt.inference.nmt_model.np.expand_dims(nmt_outputs, 0)

                batch_size = nmt_outputs.shape[1]

                for sent_id in range(batch_size):

                    # Iterate through responses
                    translations = []
                    for beam_id in range(num_translations_per_input):

                        if hparams.eos: tgt_eos = hparams.eos.encode("utf-8")

                        # Select a sentence
                        output = nmt_outputs[beam_id][sent_id, :].tolist()

                        # If there is an eos symbol in outputs, cut them at that point
                        if tgt_eos and tgt_eos in output:
                            output = output[:output.index(tgt_eos)]
                        print(output)

                        # Format response
                        if hparams.subword_option == "bpe":  # BPE
                            translation = nmt.utils.format_bpe_text(output)
                        elif hparams.subword_option == "spm":  # SPM
                            translation = nmt.utils.format_spm_text(output)
                        else:
                            translation = nmt.utils.format_text(output)

                        # Add response to the list
                        translations.append(translation.decode('utf-8'))

                    answers.append(translations)

            except tf.errors.OutOfRangeError:
                print("end")
                break

        # bug workaround end
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '0'
        sys.stdout.close()
        sys.stdout = current_stdout
        current_stdout = None

        return answers

# Fancy way to start everything on first inference() call
def start_inference(question):

    global inference_helper, inference_object

    # Start inference, set global tuple with model, flags and hparams
    inference_object = do_start_inference(out_dir, hparams)

    # First inference() call calls that method
    # Now we have everything running, so replace inference() with actual function call
    inference_helper = lambda question: do_inference(question, *inference_object)

    # Rerun inference() call
    return inference_helper(question)

# Model, flags and hparams
inference_object = None

# Function call helper (calls start_inference on first call, then do_inference)
inference_helper = start_inference

# Main inference function
def inference(questions, include_blacklisted = True):

    # Process questions
    answers_list = process_questions(questions, include_blacklisted)

    # Return (one or more?)
    if len(answers_list) == 1:
        return answers_list[0]
    else:
        return answers_list

# Internal inference function (for direct call)
def inference_internal(questions):

    # Process questions and return
    return process_questions(questions)


# Get index and score for best answer
def get_best_score(answers_score, include_blacklisted = True):

    try:
        index = answers_score.index(1)
        score = 1
    except:
        index = None

    if index is None and include_blacklisted:
        try:
            index = answers_score.index(0)
            score = 0
        except:
            index = 0
            score = -1

    if index is None:
        index = 0
        score = -1

    return (index, score)

# Process question or list of questions
def process_questions(questions, include_blacklisted = True):

    # Make a list
    if not isinstance(questions, list):
        questions = [questions]

    # Clean and tokenize
    prepared_questions = []
    for question in questions:
        question = question.strip()
        prepared_questions.append(tokenize(question) if question else '##emptyquestion##')

    # Run inference
    answers_list = inference_helper(prepared_questions)

    # Process answers
    prepared_answers_list = []
    for index, answers in enumerate(answers_list):
        answers = detokenize(answers)
        answers = replace_in_answers(answers, 'answers')
        answers_score = score_answers(answers, 'answers')
        best_index, best_score = get_best_score(answers_score, include_blacklisted)

        if prepared_questions[index] == '##emptyquestion##':
            prepared_answers_list.append(None)
        else:
            prepared_answers_list.append({'answers': answers, 'scores': answers_score, 'best_index': best_index, 'best_score': best_score})

    return prepared_answers_list

# interactive mode
if __name__ == "__main__":

    # Input file
    if sys.stdin.isatty() == False:

        # Process questions
        answers_list = process_questions(sys.stdin.readlines())

        # Print answers
        for answers in answers_list:
            print(answers['answers'][answers['best_index']])

        sys.exit()

    # Interactive mode
    print("\n\nStarting interactive mode (first response will take a while):")
    colorama.init()

    # QAs
    while True:
        question = input("\n> ")
        answers = process_questions(question)[0]
        if answers is None:
            print(colorama.Fore.RED + "! Question can't be empty")
        else:
            for i, _ in enumerate(answers['scores']):
                print("{}- {}{}".format(colorama.Fore.GREEN if answers['scores'][i] == 1 else colorama.Fore.YELLOW if answers['scores'][i] == 0 else colorama.Fore.RED, answers['answers'][i], colorama.Fore.RESET))
