import styles from './About.module.css';

export default function About() {
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.badge}>About</div>
          <h1 className={styles.title}>Multimodal Momentum Prediction</h1>
          <p className={styles.subtitle}>
            A full-stack application that fuses financial Twitter sentiment with
            quantitative market signals to forecast short-term stock momentum,
            served end-to-end through a production-grade cloud deployment.
          </p>
        </div>

        {/* Project Overview */}
        <Section title="Project Overview">
          <p className={styles.paragraph}>
            This project started as a machine learning research question: can
            combining financial Twitter sentiment with numerical market features
            produce better short-term momentum forecasts than either signal alone?
            Rather than stop at a notebook, the model was wrapped in a production
            system so that retail traders can actually interact with it, searching
            tickers, viewing predictions, and exploring charts through a web app.
          </p>
          <p className={`${styles.paragraph} ${styles.paragraphSpaced}`}>
            The result is a four-layer system: a React frontend, a Spring Boot API
            that handles user-facing logic, a Python gRPC service that runs model
            inference, and an offline data pipeline that assembles the features.
            Everything is deployed on AWS using ECS Fargate.
          </p>
        </Section>

        {/* System Architecture */}
        <Section title="System Architecture">
          <p className={styles.paragraph}>
            A user request flows through four services, each with a focused
            responsibility. This separation keeps the ML runtime independent of the
            web backend and allows each layer to scale on its own.
          </p>

          <SubSection label="01" title="React Frontend">
            The client application renders the interactive dashboard where users
            search tickers, authenticate, and view predictions alongside price
            charts. Chart components visualize both the raw market data and the
            model&apos;s momentum output so users can see the signal in context
            rather than as a bare number.
          </SubSection>

          <SubSection label="02" title="Spring Boot Backend">
            The primary application server, written in Java with Spring Boot. It
            handles user login and session management, fetches ticker data from a
            market data API, shapes and aggregates data for the frontend charts,
            and orchestrates calls to the ML service. Effectively every user-facing
            action passes through this layer, and the frontend never talks to the
            ML service directly.
          </SubSection>

          <SubSection label="03" title="gRPC Inference Service">
            A Python gRPC server whose sole job is running the trained model. The
            Spring Boot backend sends a feature payload over gRPC and the service
            returns a momentum prediction. Keeping inference isolated behind a
            typed gRPC contract means the model can be retrained, swapped, or
            scaled independently of the rest of the app, and the Java backend gets
            a strict interface to code against.
          </SubSection>

          <SubSection label="04" title="Data Pipeline">
            An offline pipeline is responsible for collecting the raw inputs that
            feed the model: financial tweets for the sentiment tower, and ticker
            information from a market data API for the numerical towers. This
            work is done outside the request path so inference stays fast and does
            not depend on third-party API latency at serve time.
          </SubSection>
        </Section>

        {/* Machine Learning Model */}
        <Section title="Machine Learning Model">
          <p className={styles.paragraph}>
            The model is organized as three parallel towers whose outputs are fused
            into a single representation before being passed to a regression head.
            Each tower specializes in one modality.
          </p>

          <SubSection label="01" title="Sentiment Encoder Tower">
            Uses the pretrained <Mono>FinTwitBERT</Mono> encoder from Hugging Face,
            trained specifically on financial Twitter data to capture its unique
            dialect. It produces 768-dimensional embeddings; on days with multiple
            tweets, the [CLS] vectors are mean-pooled to preserve that
            dimensionality. The encoder is frozen during training due to
            computational constraints.
          </SubSection>

          <SubSection label="02" title="Stock Neural Network Tower">
            A deep network that ingests a 37-dimensional per-stock input and passes
            it through two hidden layers (128 then 64) before producing a
            32-dimensional output. LeakyReLU (alpha 0.01) activations prevent
            vanishing gradients, and a dropout layer after the first activation
            helps mitigate overfitting.
          </SubSection>

          <SubSection label="03" title="Market Index Neural Network Tower">
            Mirrors the stock tower&apos;s design with different dimensions. It
            takes a 42-dimensional input, passes through hidden layers of size 64
            and 32, and outputs a 16-dimensional embedding, also using LeakyReLU
            activations and dropout.
          </SubSection>

          <SubSection label="04" title="Fusion and Output">
            A learnable projection reduces the encoder&apos;s 768-dimensional
            output to 32 dimensions so it does not dominate the fused
            representation. The three towers are then concatenated into an
            80-dimensional fused embedding (32 stock plus 16 index plus 32
            projected encoder), with the stock tower contributing over half of the
            signal. Three regression heads (linear, shallow with one 64-unit
            hidden layer, and deep with 64 and 32 hidden layers) each output a
            single scalar representing predicted momentum.
          </SubSection>

          <h3 className={styles.subheading}>Training Setup</h3>
          <p className={styles.paragraph}>
            The model is trained with a <Mono>weighted Huber loss</Mono> and L1
            regularization, where class weights are proportional to the number of
            up-days and down-days in each fold to handle natural market imbalance.
            Training runs for up to 50 epochs with early stopping (minimum 20
            epochs, patience of 10) driven by validation R squared.
          </p>

          <div className={styles.statGrid}>
            <StatCard label="Tower LR" value="2e-5" note="Stock and market networks" />
            <StatCard label="Head LR" value="2e-4" note="Regression output head" />
            <StatCard
              label="Early stopping"
              value={<>R<sup>2</sup> validation</>}
              note="20 epoch minimum, with 10 epoch patience"
            />
            <StatCard label="Dropout" value="0.2" note="Applied across modules" />
            <StatCard label="L1 Regularization" value=".001" note="Applied to Huber loss" />
            <StatCard label="Optimizer" value="AdamW" note="Weight decay 1e-4 / 1e-2" />
          </div>

          <p className={`${styles.paragraph} ${styles.paragraphSpaced}`}>
            Because the encoder is frozen, gradients flow only through the stock
            tower, market tower, and regression head.
          </p>
        </Section>

        {/* Deployment */}
        <Section title="Deployment">
          <p className={styles.paragraph}>
            The system is deployed on AWS with the two application services
            running as containerized workloads on <Mono>ECS Fargate</Mono>. Fargate
            was chosen so the cluster is fully serverless, with no EC2 instances
            to patch or right-size, and each service scales on its own based on
            load.
          </p>

          <SubSection label="01" title="Spring Boot on ECS Fargate">
            The Java backend runs as a Fargate task exposed to the internet through
            a load balancer. This is the public entry point for the React
            frontend. Sizing the backend independently of the model service means
            traffic spikes to the dashboard do not force the GPU or ML-bound
            service to scale alongside it.
          </SubSection>

          <SubSection label="02" title="gRPC Inference on ECS Fargate">
            The Python inference service runs as a separate Fargate task reachable
            only from within the private network. Keeping it internal means the
            model is never directly exposed to the public internet, and every
            request arrives through the authenticated Spring Boot layer.
          </SubSection>

          <SubSection label="03" title="Service-to-Service Communication">
            The Spring Boot backend calls the gRPC service over the internal VPC
            network using a typed protobuf contract. gRPC&apos;s binary framing and
            code generation make the Java-to-Python boundary feel like a normal
            typed method call instead of a hand-rolled REST integration.
          </SubSection>
        </Section>
      </div>
    </div>
  );
}

/* ---------- Small components ---------- */

function Section({ title, children }) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

function SubSection({ label, title, children }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardLabel}>{label}</span>
        <h3 className={styles.cardTitle}>{title}</h3>
      </div>
      <p className={styles.cardBody}>{children}</p>
    </div>
  );
}

function StatCard({ label, value, note }) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statNote}>{note}</div>
    </div>
  );
}

function Mono({ children }) {
  return <code className={styles.mono}>{children}</code>;
}